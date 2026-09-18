"""Image Scanner — OCR adapter that delegates verification to NewsVerifier.

Architecture:
    Image → prepare_image() → Gemini Vision OCR → clean_ocr_text() → NewsVerifier.verify() → wrap response

The Image Scanner is NOT a second verification engine.  Its job is:
    See → Read → Lightly clean → Hand off.

The NewsVerifier's job is:
    Understand claims → Search → Gather evidence → Analyze → Adjudicate → Verdict.
"""

import asyncio
import base64
import json
import logging
import math
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from collections.abc import Callable
from io import BytesIO
from typing import Any

import httpx
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

from app.FakeNewsAnalyzer.news_verifier import NewsVerifier
from app.Global.config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_IMAGE_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
    "HEIF": "image/heif",
    "HEIC": "image/heic",
}

# NewsVerifier verdict → user-facing classification
_VERDICT_TO_CLASSIFICATION: dict[str, str] = {
    "VERIFIED": "REAL",
    "LIKELY_TRUE": "REAL",
    "MISLEADING": "MISLEADING",
    "UNVERIFIED": "INSUFFICIENT_EVIDENCE",
    "LIKELY_FALSE": "FAKE",
    "FALSE": "FAKE",
    "SATIRE": "SATIRE",
    "OUTDATED": "MISLEADING",
}

_VERDICT_TO_OVERALL: dict[str, str] = {
    "VERIFIED": "SUPPORTED",
    "LIKELY_TRUE": "MOSTLY_SUPPORTED",
    "MISLEADING": "MISLEADING",
    "UNVERIFIED": "UNVERIFIABLE",
    "LIKELY_FALSE": "MOSTLY_FALSE",
    "FALSE": "FALSE",
    "SATIRE": "UNVERIFIABLE",
    "OUTDATED": "NEEDS_CONTEXT",
}

# Minimum meaningful text thresholds
_MIN_WORD_COUNT = 3
_MIN_CHAR_COUNT = 15

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ImagePreprocessingError(ValueError):
    """Raised when an upload is not a safe, supported image."""


class OcrUnavailableError(RuntimeError):
    """Raised when the primary OCR runtime is not installed or cannot load."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PreparedImage:
    original_bytes: bytes
    processed: Any
    mime_type: str
    width: int
    height: int


@dataclass(frozen=True)
class OcrSegment:
    text: str
    confidence: float
    bounding_box: list[list[float]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "bounding_box": self.bounding_box,
            "engine": "paddleocr",
        }


# ---------------------------------------------------------------------------
# Image preprocessing
# ---------------------------------------------------------------------------


def _register_heif_opener() -> None:
    try:
        from pillow_heif import register_heif_opener
    except ImportError:
        return
    register_heif_opener()


def prepare_image(
    image_bytes: bytes,
    *,
    max_pixels: int,
    max_source_pixels: int = 80_000_000,
) -> PreparedImage:
    """Decode an upload and produce one bounded-size, three-channel OCR array."""
    _register_heif_opener()
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image_format = (image.format or "").upper()
            width, height = image.size
            if image_format not in ALLOWED_IMAGE_FORMATS:
                raise ImagePreprocessingError(
                    "Only JPEG, PNG, WEBP, GIF, HEIC, and HEIF images are supported"
                )
            source_pixels = width * height
            if width < 20 or height < 20:
                raise ImagePreprocessingError("The image dimensions are unsupported")
            if source_pixels > max_source_pixels:
                raise ImagePreprocessingError("The decoded image dimensions are too large")

            scale = min(3.0, max(1.0, 1800 / max(width, height)))
            if source_pixels * scale * scale > max_pixels:
                scale = math.sqrt(max_pixels / source_pixels)
            target_size = (
                max(20, round(width * scale)),
                max(20, round(height * scale)),
            )

            if image_format == "JPEG":
                image.draft("RGB", target_size)
            if image_format == "GIF":
                image.seek(0)
            image.thumbnail(target_size, Image.Resampling.LANCZOS)
            oriented = ImageOps.exif_transpose(image)
            if "A" in oriented.getbands():
                rgba = oriented.convert("RGBA")
                rgb = Image.new("RGB", rgba.size, "white")
                rgb.paste(rgba, mask=rgba.getchannel("A"))
            else:
                rgb = oriented.convert("RGB")

            vision_bytes = image_bytes
            vision_mime = ALLOWED_IMAGE_FORMATS[image_format]
            if image_format in {"GIF", "HEIF", "HEIC"}:
                normalized = BytesIO()
                rgb.save(normalized, format="JPEG", quality=92, optimize=True)
                vision_bytes = normalized.getvalue()
                vision_mime = "image/jpeg"

            gray = ImageOps.grayscale(rgb)
            contrast = ImageOps.autocontrast(gray, cutoff=1)
            sharpened = contrast.filter(
                ImageFilter.UnsharpMask(radius=1.0, percent=35, threshold=3)
            )
    except ImagePreprocessingError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImagePreprocessingError("The upload is not a valid image") from exc

    try:
        import numpy as np
    except ImportError as exc:
        raise OcrUnavailableError("NumPy is not installed") from exc

    gray_array = np.asarray(sharpened)
    processed = np.repeat(gray_array[:, :, np.newaxis], 3, axis=2)
    return PreparedImage(
        original_bytes=vision_bytes,
        processed=processed,
        mime_type=vision_mime,
        width=width,
        height=height,
    )


# ---------------------------------------------------------------------------
# PaddleOCR engine (fallback only)
# ---------------------------------------------------------------------------


class PaddleOcrEngine:
    """Lazy PaddleOCR adapter supporting both the v2 `ocr` and v3 `predict` APIs."""

    def __init__(self, language: str) -> None:
        self.language = language
        self._engine: Any | None = None
        self._load_lock = threading.Lock()
        self._inference_lock = threading.Lock()

    def _load(self) -> Any:
        if self._engine is not None:
            return self._engine
        with self._load_lock:
            if self._engine is not None:
                return self._engine
            try:
                # On Windows, Paddle may load DLLs that prevent PyTorch's shm.dll
                # from resolving later. PaddleOCR imports ModelScope (and therefore
                # PyTorch), so load PyTorch first to keep both analyzers usable in
                # the same API process.
                import torch
                from paddleocr import PaddleOCR

                _ = torch.__version__

                try:
                    self._engine = PaddleOCR(
                        lang=self.language,
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_textline_orientation=True,
                    )
                except (TypeError, ValueError):
                    self._engine = PaddleOCR(
                        lang=self.language,
                        use_angle_cls=True,
                        show_log=False,
                    )
            except (ImportError, OSError, RuntimeError) as exc:
                logger.exception("Unable to load PaddleOCR")
                raise OcrUnavailableError("PaddleOCR is unavailable") from exc
        return self._engine

    def transcribe(self, image: Any) -> list[OcrSegment]:
        engine = self._load()
        try:
            with self._inference_lock:
                if hasattr(engine, "predict"):
                    output = list(engine.predict(image))
                else:
                    output = engine.ocr(image, cls=True)
            segments = _parse_paddle_output(output)
            return sorted(segments, key=_reading_order_key)
        except OcrUnavailableError:
            raise
        except (RuntimeError, ValueError, TypeError, KeyError, IndexError) as exc:
            logger.exception("PaddleOCR inference failed")
            raise OcrUnavailableError("PaddleOCR could not process this image") from exc

    def warmup(self) -> None:
        self._load()


def _parse_paddle_output(output: Any) -> list[OcrSegment]:
    segments: list[OcrSegment] = []
    for result in output or []:
        payload = getattr(result, "json", result)
        if callable(payload):
            payload = payload()
        if isinstance(payload, dict):
            payload = payload.get("res", payload)
            texts = payload.get("rec_texts", [])
            scores = payload.get("rec_scores", [])
            boxes = payload.get("dt_polys", payload.get("rec_polys", []))
            for text, score, box in zip(texts, scores, boxes, strict=False):
                if str(text).strip():
                    segments.append(_segment(str(text), score, box))
            continue

        lines = result if isinstance(result, list) else []
        if lines and _looks_like_ocr_line(lines):
            lines = [lines]
        for line in lines:
            if not _looks_like_ocr_line(line):
                continue
            box, recognition = line[0], line[1]
            text, score = recognition[0], recognition[1]
            if str(text).strip():
                segments.append(_segment(str(text), score, box))
    return segments


def _looks_like_ocr_line(value: Any) -> bool:
    return (
        isinstance(value, list | tuple)
        and len(value) >= 2
        and isinstance(value[1], list | tuple)
        and len(value[1]) >= 2
        and isinstance(value[1][0], str)
    )


def _segment(text: str, score: Any, box: Any) -> OcrSegment:
    points = []
    for point in list(box) if box is not None else []:
        if isinstance(point, list | tuple) or hasattr(point, "tolist"):
            values = point.tolist() if hasattr(point, "tolist") else point
            if len(values) >= 2:
                points.append([float(values[0]), float(values[1])])
    return OcrSegment(text=" ".join(text.split()), confidence=float(score), bounding_box=points)


def _reading_order_key(segment: OcrSegment) -> tuple[float, float]:
    if not segment.bounding_box:
        return (0.0, 0.0)
    return (
        min(point[1] for point in segment.bounding_box),
        min(point[0] for point in segment.bounding_box),
    )


# ---------------------------------------------------------------------------
# Gemini Vision client
# ---------------------------------------------------------------------------


class GeminiVisionClient:
    """Gemini Vision API client for OCR transcription."""

    TRANSCRIPTION_PROMPT = (
        "Transcribe all visible text exactly as shown. Do not summarize. Do not fact-check. "
        "Do not correct factual claims. Do not add missing information. Preserve numbers, names, "
        "symbols, capitalization, line breaks, and wording as accurately as possible. If a word "
        "is unreadable, write [UNCLEAR] instead of guessing. Return only the transcription."
    )

    STRUCTURED_OCR_PROMPT = (
        "You are an OCR transcription engine. Read ALL text visible in this image exactly as "
        "shown. Do not summarize, fact-check, interpret, correct factual claims, or add "
        "information not visible in the image.\n\n"
        "Preserve exactly: numbers, names, symbols, dates, locations, capitalization, tense, "
        "negation, attribution, modality, and wording.\n\n"
        "For each text region, categorize it as: headline, body, caption, label, watermark, "
        "ui_element, or other. Distinguish primary news content from UI elements, watermarks, "
        "logos, timestamps, buttons, usernames, and decorative text.\n\n"
        "In raw_text, concatenate ALL meaningful text (excluding UI/watermark). "
        "Provide your best estimate of overall OCR accuracy as confidence (0.0 to 1.0). "
        "If you cannot reliably estimate confidence, omit it.\n\n"
        "Return ONLY the requested JSON."
    )

    STRUCTURED_OCR_SCHEMA = {
        "type": "OBJECT",
        "properties": {
            "raw_text": {"type": "STRING"},
            "blocks": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "text": {"type": "STRING"},
                        "type": {
                            "type": "STRING",
                            "enum": [
                                "headline",
                                "body",
                                "caption",
                                "label",
                                "watermark",
                                "ui_element",
                                "other",
                            ],
                        },
                    },
                    "required": ["text", "type"],
                },
            },
            "confidence": {"type": "NUMBER"},
        },
        "required": ["raw_text", "blocks"],
    }

    def __init__(self, settings: Settings) -> None:
        configured_keys = getattr(settings, "gemini_api_key_list", None)
        if configured_keys is None:
            legacy_key = getattr(settings, "gemini_api_key", None)
            configured_keys = (
                [legacy_key.get_secret_value()]
                if legacy_key is not None and legacy_key.get_secret_value()
                else []
            )
        self.api_keys = list(dict.fromkeys(configured_keys))
        self.model = settings.gemini_vision_model
        self.timeout = settings.gemini_timeout_seconds
        self.key_cooldown_seconds = getattr(settings, "gemini_key_cooldown_seconds", 60)
        self._next_key_index = 0
        self._key_lock = asyncio.Lock()
        self._cooldowns: dict[str, float] = {}
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=5),
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_keys)

    async def _available_keys(self) -> list[str]:
        now = time.monotonic()
        async with self._key_lock:
            start = self._next_key_index % len(self.api_keys)
            self._next_key_index = (start + 1) % len(self.api_keys)
            ordered = self.api_keys[start:] + self.api_keys[:start]
            return [key for key in ordered if self._cooldowns.get(key, 0.0) <= now]

    async def _cool_down(self, key: str, status_code: int) -> None:
        cooldown = 3_600 if status_code in {400, 401, 403} else self.key_cooldown_seconds
        async with self._key_lock:
            self._cooldowns[key] = time.monotonic() + cooldown

    @staticmethod
    def _is_key_failure(response: httpx.Response) -> bool:
        if response.status_code in {401, 403, 429}:
            return True
        return response.status_code == 400 and "api key" in response.text.casefold()

    async def generate(
        self,
        image: PreparedImage | None,
        prompt: str,
        *,
        generation_config: dict[str, Any] | None = None,
        model: str | None = None,
        validate_text: Callable[[str], Any] | None = None,
    ) -> str:
        if not self.configured:
            raise OcrUnavailableError("Gemini Vision is not configured")
        keys = await self._available_keys()
        if not keys:
            raise OcrUnavailableError("All Gemini API keys are temporarily cooling down")

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model or self.model}:generateContent"
        )
        parts: list[dict[str, Any]] = [{"text": prompt}]
        if image is not None:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": image.mime_type,
                        "data": base64.b64encode(image.original_bytes).decode("ascii"),
                    }
                }
            )
        payload = {
            "contents": [
                {
                    "parts": parts,
                }
            ],
            "generationConfig": generation_config
            or {
                "temperature": 0,
                "maxOutputTokens": 4096,
                "thinkingConfig": {"thinkingLevel": "minimal"},
            },
        }
        last_error: Exception | None = None
        for position, api_key in enumerate(keys, start=1):
            # Another concurrent request may have cooled this key since selection.
            if self._cooldowns.get(api_key, 0.0) > time.monotonic():
                continue
            try:
                response = await self._client.post(
                    url,
                    headers={"x-goog-api-key": api_key},
                    json=payload,
                )
            except httpx.TransportError as exc:
                last_error = exc
                continue
            if self._is_key_failure(response):
                await self._cool_down(api_key, response.status_code)
                logger.warning(
                    "Gemini credential %d/%d was rejected with HTTP %d; trying the next key",
                    position,
                    len(keys),
                    response.status_code,
                )
                last_error = httpx.HTTPStatusError(
                    "Gemini credential rejected",
                    request=response.request,
                    response=response,
                )
                continue
            try:
                response.raise_for_status()
                data = response.json()
                candidates = data.get("candidates") or [{}]
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "\n".join(str(part.get("text", "")) for part in parts).strip()
                if not text:
                    raise ValueError("Gemini returned no usable text")
                if validate_text is not None:
                    validate_text(text)
                return text
            except (httpx.HTTPStatusError, ValueError) as exc:
                last_error = exc
                continue

        if last_error is not None:
            raise last_error
        raise OcrUnavailableError("No Gemini API key is currently available")

    async def transcribe(self, image: PreparedImage) -> str:
        """Plain-text transcription of all visible text in the image."""
        if not self.configured:
            return ""
        text = await self.generate(image, self.TRANSCRIPTION_PROMPT)
        return re.sub(r"^```(?:text)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()

    async def transcribe_structured(self, image: PreparedImage) -> dict[str, Any]:
        """Structured OCR returning raw_text, categorized blocks, and confidence."""
        if not self.configured:
            return {"raw_text": "", "blocks": [], "confidence": None}
        try:
            raw = await self.generate(
                image,
                self.STRUCTURED_OCR_PROMPT,
                generation_config={
                    "temperature": 0,
                    "maxOutputTokens": 4096,
                    "thinkingConfig": {"thinkingLevel": "minimal"},
                    "responseMimeType": "application/json",
                    "responseSchema": self.STRUCTURED_OCR_SCHEMA,
                },
            )
            result = json.loads(raw)
            raw_text = str(result.get("raw_text", "")).strip()
            blocks = [
                {"text": str(b.get("text", "")), "type": str(b.get("type", "body"))}
                for b in result.get("blocks", [])
                if str(b.get("text", "")).strip()
            ]
            confidence = result.get("confidence")
            if confidence is not None:
                confidence = max(0.0, min(1.0, float(confidence)))
            return {"raw_text": raw_text, "blocks": blocks, "confidence": confidence}
        except (json.JSONDecodeError, ValueError, KeyError):
            logger.warning(
                "Structured OCR failed; falling back to plain transcription", exc_info=True
            )
            text = await self.transcribe(image)
            return {
                "raw_text": text,
                "blocks": [{"text": text, "type": "body"}] if text.strip() else [],
                "confidence": None,
            }

    async def aclose(self) -> None:
        await self._client.aclose()


# ---------------------------------------------------------------------------
# AI-generated image detector (ISOLATED — not part of verification pipeline)
#
# This class is used ONLY by the /detector/image endpoint for the separate
# AI-content-detection feature.  It must NOT influence factual verdicts.
# ---------------------------------------------------------------------------


class GeminiImageDetector:
    """Visual signal assessment backed by Gemini's multimodal image understanding."""

    PROMPT = (
        "Assess this image for visible signals associated with AI generation or digital "
        "manipulation. Inspect geometry, anatomy, text rendering, repeated textures, lighting, "
        "shadows, reflections, boundaries, perspective, and internal semantic consistency. "
        "Do not claim access to metadata or invisible forensic evidence. A normal-looking image "
        "is not proof of authenticity. Return only the requested JSON object."
    )
    RESPONSE_SCHEMA = {
        "type": "OBJECT",
        "properties": {
            "classification": {
                "type": "STRING",
                "enum": [
                    "Likely AI-generated",
                    "Likely authentic/camera-captured",
                    "Manipulation suspected",
                    "Inconclusive",
                ],
            },
            "confidence": {"type": "INTEGER", "minimum": 0, "maximum": 100},
            "ai_probability": {"type": "INTEGER", "minimum": 0, "maximum": 100},
            "summary": {"type": "STRING"},
            "signals": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "maxItems": 6,
            },
            "limitations": {"type": "STRING"},
        },
        "required": [
            "classification",
            "confidence",
            "ai_probability",
            "summary",
            "signals",
            "limitations",
        ],
    }

    def __init__(self, client: GeminiVisionClient) -> None:
        self.client = client

    @property
    def configured(self) -> bool:
        return self.client.configured

    async def analyze(self, image: PreparedImage) -> dict[str, Any]:
        raw = await self.client.generate(
            image,
            self.PROMPT,
            generation_config={
                "temperature": 0,
                "maxOutputTokens": 1024,
                "thinkingConfig": {"thinkingLevel": "minimal"},
                "responseMimeType": "application/json",
                "responseSchema": self.RESPONSE_SCHEMA,
            },
        )
        result = json.loads(raw)
        ai_probability = max(0, min(100, int(result["ai_probability"])))
        confidence = max(0, min(100, int(result["confidence"])))
        return {
            "classification": str(result["classification"]),
            "confidence": confidence,
            "ai_probability": ai_probability,
            "authentic_probability": 100 - ai_probability,
            "summary": str(result["summary"]).strip(),
            "signals": [str(item).strip() for item in result["signals"] if str(item).strip()][:6],
            "limitations": str(result["limitations"]).strip(),
            "model": getattr(self.client, "model", "gemini-vision"),
        }


# ---------------------------------------------------------------------------
# OCR evaluation helpers
# ---------------------------------------------------------------------------


def _critical_text(value: str) -> bool:
    return bool(
        re.search(r"[₱%\d]", value)
        or re.search(r"\b[A-Z]{2,}\b", value)
        or re.search(
            r"\b(?:Jan(?:uary)?|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b",
            value,
            re.IGNORECASE,
        )
        or re.search(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b", value)
    )


def evaluate_ocr(
    segments: list[OcrSegment], *, medium_threshold: float, high_threshold: float
) -> tuple[float, str, list[dict[str, object]], bool]:
    total_weight = sum(max(len(segment.text), 1) for segment in segments)
    confidence = (
        sum(segment.confidence * max(len(segment.text), 1) for segment in segments) / total_weight
        if total_weight
        else 0.0
    )
    quality = "HIGH" if confidence >= high_threshold else "MEDIUM"
    if confidence < medium_threshold:
        quality = "LOW"
    uncertain = [
        {
            "text": segment.text,
            "confidence": round(segment.confidence, 4),
            "bounding_box": segment.bounding_box,
            "critical": _critical_text(segment.text),
        }
        for segment in segments
        if segment.confidence < medium_threshold
    ]
    critical_uncertain = any(bool(item["critical"]) for item in uncertain)
    fallback_needed = not segments or quality == "LOW" or critical_uncertain
    return confidence, quality, uncertain, fallback_needed


# ---------------------------------------------------------------------------
# Deterministic OCR text cleanup
# ---------------------------------------------------------------------------


def clean_ocr_text(text: str) -> str:
    """Clean common OCR artifacts from extracted text before verification.

    Performs only safe, deterministic cleanup:
    - Unicode normalization and non-breaking spaces
    - Hyphenated words broken across line breaks
    - Broken lines within continuous sentences
    - Excessive whitespace and repeated blank lines
    - Repeated punctuation artifacts
    - Non-text artifacts at edges

    Does NOT perform semantic rewriting, entity canonicalization,
    tense changes, or any modification that could alter factual meaning.
    """
    if not text:
        return ""
    cleaned = unicodedata.normalize("NFKC", text).replace("\u00a0", " ")
    # Rejoin words broken by a hyphen or dash at line-end
    cleaned = re.sub(r"(\w+)[-–—]\s*\n\s*(\w+)", r"\1\2", cleaned)
    # Rejoin lines broken mid-sentence (lowercase word, number, or comma continuation)
    cleaned = re.sub(r"(?<=[^\n.!?])\n(?=[a-z0-9,])", " ", cleaned)
    # Collapse multiple whitespace characters (excluding double newlines for paragraph breaks)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    # Normalize repeated punctuation
    cleaned = re.sub(r"\.{4,}", "...", cleaned)
    cleaned = re.sub(r"!{2,}", "!", cleaned)
    cleaned = re.sub(r"\?{2,}", "?", cleaned)
    cleaned = re.sub(r"[-—–]{2,}", "—", cleaned)
    # Fix common OCR spacing artifacts in currency and numbers
    cleaned = re.sub(r"₱\s+(\d)", r"₱\1", cleaned)
    cleaned = re.sub(r"(\d)\s+(\d{3})\b", r"\1\2", cleaned)
    # Strip non-text artifacts from edges
    cleaned = re.sub(r"^[\s\-_~|•*#—–\u2022\u25cf\u25cb\ufffd]+|[\s\-_~|•*#—–\u2022\u25cf\u25cb\ufffd]+$", "", cleaned)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Text meaningfulness check
# ---------------------------------------------------------------------------


def _has_meaningful_text(text: str) -> bool:
    """Determine whether OCR output contains enough text for news verification."""
    if not text or not text.strip():
        return False
    cleaned = text.strip()
    words = cleaned.split()
    if len(words) < _MIN_WORD_COUNT:
        return False
    if len(cleaned) < _MIN_CHAR_COUNT:
        return False
    # Reject text that is all symbols/numbers with no actual words
    alpha_words = [w for w in words if re.search(r"[a-zA-Z\u00C0-\u024F]", w)]
    if len(alpha_words) < 2:
        return False
    return True


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


def _build_image_response(
    ocr_result: dict[str, Any],
    verification: dict[str, Any],
    timing: dict[str, float],
) -> dict[str, Any]:
    """Wrap the NewsVerifier result with OCR and image metadata."""
    verdict = verification.get("verdict", "UNVERIFIED")
    confidence = int(verification.get("confidence", 0))
    classification = _VERDICT_TO_CLASSIFICATION.get(verdict, "INSUFFICIENT_EVIDENCE")
    overall_verdict = _VERDICT_TO_OVERALL.get(verdict, "UNVERIFIABLE")
    overall_confidence = "HIGH" if confidence >= 80 else "MEDIUM" if confidence >= 55 else "LOW"
    explanation = str(verification.get("explanation", ""))

    evidence_groups = verification.get("evidence", {}) or {}
    supporting = evidence_groups.get("supporting", []) or []
    contradicting = evidence_groups.get("contradicting", []) or []
    debunks = evidence_groups.get("debunks", []) or []
    related = evidence_groups.get("related", []) or []
    all_evidence = debunks + contradicting + supporting + related

    mapped_evidence = []
    for ev in all_evidence:
        rel = ev.get("relationship", "RELATED")
        mapped_rel = (
            "CONTRADICTS"
            if rel in ("CONTRADICTS", "DEBUNKS")
            else "SUPPORTS"
            if rel == "SUPPORTS"
            else "PARTIAL"
        )
        mapped_evidence.append(
            {
                "title": ev.get("title", "") or ev.get("snippet", ""),
                "source": ev.get("source", "") or ev.get("domain", ""),
                "source_type": ev.get("source_type", "MAJOR_NEWS"),
                "url": ev.get("url", ""),
                "publication_date": ev.get("publication_date", "") or ev.get("date", ""),
                "relationship": mapped_rel,
                "similarity": ev.get("similarity", 50),
                "reason": ev.get("reason", "") or ev.get("snippet", ""),
            }
        )

    atomic_claims = verification.get("atomic_claims", []) or [ocr_result.get("cleaned_text", "")]
    claims = [
        {
            "claim_id": f"claim-{i+1}",
            "claim": c,
            "original_claim": c,
            "normalized_claim": c,
            "claim_type": "FACTUAL_NEWS",
            "ocr_confidence": overall_confidence,
            "evidence": mapped_evidence,
            "context_warnings": verification.get("context_warnings", []) or [],
            "verdict": verdict,
            "confidence": confidence,
            "explanation": explanation,
        }
        for i, c in enumerate(atomic_claims)
    ]

    extracted_blocks = ocr_result.get("blocks", []) or []
    headline = ""
    for block in extracted_blocks:
        if block.get("type") == "headline":
            headline = block.get("text", "")
            break
    if not headline and extracted_blocks:
        headline = extracted_blocks[0].get("text", "")

    extracted = {
        "headline": headline,
        "body_text": ocr_result.get("cleaned_text", ""),
        "publisher": "",
        "speaker": "",
        "quote": "",
        "date": "",
        "entities": [],
    }

    closest_story = verification.get("closest_real_story")
    closest_real_dict = (
        closest_story.model_dump()
        if hasattr(closest_story, "model_dump")
        else (closest_story if isinstance(closest_story, dict) else None)
    )

    return {
        "input_type": "image",
        "status": "success",
        "ocr": {
            "raw_text": ocr_result.get("raw_text", ""),
            "cleaned_text": ocr_result.get("cleaned_text", ""),
            "blocks": ocr_result.get("blocks", []),
            "confidence": ocr_result.get("confidence"),
            "provider": ocr_result.get("provider", "gemini"),
            "fallback_used": ocr_result.get("fallback_used", False),
        },
        "verification": verification,
        "metadata": {
            "ocr_provider": ocr_result.get("provider", "gemini"),
            "verification_engine": "NewsVerifier",
            "timing": timing,
        },
        # Top-level convenience fields
        "classification": classification,
        "confidence": confidence,
        "overall_verdict": overall_verdict,
        "overall_confidence": overall_confidence,
        "reasoning_summary": explanation,
        "user_explanation": f"{classification} — {confidence}% confidence\n\n{explanation}",
        "recommendation": _recommendation(classification, verification),
        # Compatibility fields for frontend / existing clients
        "summary": explanation,
        "claims": claims,
        "extracted": extracted,
        "quote_verification": {
            "is_quote": False,
            "speaker": "",
            "attribution": "UNVERIFIED",
            "context": "UNKNOWN",
        },
        "date_analysis": {
            "post_date": "",
            "event_date": "",
            "source_dates": [],
            "consistent": True,
            "notes": "",
        },
        "primary_source_found": bool(supporting or contradicting),
        "independent_corroboration_count": len(supporting),
        "credible_contradiction_found": bool(contradicting or debunks),
        "key_context": verification.get("context_warnings", []) or [],
        "closest_real_story": closest_real_dict,
    }


def _insufficient_text_response(
    ocr_result: dict[str, Any],
    timing: dict[str, float],
) -> dict[str, Any]:
    """Return a structured response when the image contains no meaningful text."""
    msg = (
        "No meaningful textual claim could be extracted from the image "
        "for news verification."
    )
    return {
        "input_type": "image",
        "status": "insufficient_text",
        "ocr": {
            "raw_text": ocr_result.get("raw_text", ""),
            "cleaned_text": ocr_result.get("cleaned_text", ""),
            "blocks": ocr_result.get("blocks", []),
            "confidence": ocr_result.get("confidence"),
            "provider": ocr_result.get("provider", "gemini"),
            "fallback_used": ocr_result.get("fallback_used", False),
        },
        "verification": None,
        "metadata": {
            "ocr_provider": ocr_result.get("provider", "gemini"),
            "verification_engine": "NewsVerifier",
            "timing": timing,
        },
        "classification": "INSUFFICIENT_EVIDENCE",
        "confidence": 0,
        "overall_verdict": "UNVERIFIABLE",
        "overall_confidence": "LOW",
        "reasoning_summary": msg,
        "user_explanation": f"INSUFFICIENT_EVIDENCE — 0% confidence\n\n{msg}",
        "recommendation": (
            "This image does not contain sufficient text for automated fact-checking. "
            "If there is a claim associated with this image, submit it as text instead."
        ),
        "summary": msg,
        "claims": [],
        "extracted": {
            "headline": "",
            "body_text": ocr_result.get("cleaned_text", ""),
            "publisher": "",
            "speaker": "",
            "quote": "",
            "date": "",
            "entities": [],
        },
        "quote_verification": {
            "is_quote": False,
            "speaker": "",
            "attribution": "UNVERIFIED",
            "context": "UNKNOWN",
        },
        "date_analysis": {
            "post_date": "",
            "event_date": "",
            "source_dates": [],
            "consistent": True,
            "notes": "",
        },
        "primary_source_found": False,
        "independent_corroboration_count": 0,
        "credible_contradiction_found": False,
        "key_context": [],
        "closest_real_story": None,
    }


def _ocr_failed_response(timing: dict[str, float]) -> dict[str, Any]:
    """Return a structured response when all OCR systems fail."""
    msg = "OCR text extraction failed for this image."
    return {
        "input_type": "image",
        "status": "ocr_failed",
        "ocr": {
            "raw_text": "",
            "cleaned_text": "",
            "blocks": [],
            "confidence": None,
            "provider": "none",
            "fallback_used": False,
        },
        "verification": None,
        "metadata": {
            "ocr_provider": "none",
            "verification_engine": "NewsVerifier",
            "timing": timing,
        },
        "classification": "INSUFFICIENT_EVIDENCE",
        "confidence": 0,
        "overall_verdict": "UNVERIFIABLE",
        "overall_confidence": "LOW",
        "reasoning_summary": msg,
        "user_explanation": f"INSUFFICIENT_EVIDENCE — 0% confidence\n\n{msg}",
        "recommendation": (
            "Text could not be extracted from this image. "
            "If there is a claim in this image, please type it as text instead."
        ),
        "summary": msg,
        "claims": [],
        "extracted": {
            "headline": "",
            "body_text": "",
            "publisher": "",
            "speaker": "",
            "quote": "",
            "date": "",
            "entities": [],
        },
        "quote_verification": {
            "is_quote": False,
            "speaker": "",
            "attribution": "UNVERIFIED",
            "context": "UNKNOWN",
        },
        "date_analysis": {
            "post_date": "",
            "event_date": "",
            "source_dates": [],
            "consistent": True,
            "notes": "",
        },
        "primary_source_found": False,
        "independent_corroboration_count": 0,
        "credible_contradiction_found": False,
        "key_context": [],
        "closest_real_story": None,
    }


def _verification_error_response(
    ocr_result: dict[str, Any],
    timing: dict[str, float],
    exc: Exception,
) -> dict[str, Any]:
    """Return a structured response when NewsVerifier fails."""
    msg = (
        "Verification could not be completed due to a service error. "
        "The image has not been classified as fake."
    )
    return {
        "input_type": "image",
        "status": "verification_error",
        "ocr": {
            "raw_text": ocr_result.get("raw_text", ""),
            "cleaned_text": ocr_result.get("cleaned_text", ""),
            "blocks": ocr_result.get("blocks", []),
            "confidence": ocr_result.get("confidence"),
            "provider": ocr_result.get("provider", "gemini"),
            "fallback_used": ocr_result.get("fallback_used", False),
        },
        "verification": None,
        "metadata": {
            "ocr_provider": ocr_result.get("provider", "gemini"),
            "verification_engine": "NewsVerifier",
            "timing": timing,
        },
        "classification": "INSUFFICIENT_EVIDENCE",
        "confidence": 0,
        "overall_verdict": "UNVERIFIABLE",
        "overall_confidence": "LOW",
        "reasoning_summary": msg,
        "user_explanation": f"INSUFFICIENT_EVIDENCE — 0% confidence\n\n{msg}",
        "recommendation": "Please try again later.",
        "summary": msg,
        "claims": [],
        "extracted": {
            "headline": "",
            "body_text": ocr_result.get("cleaned_text", ""),
            "publisher": "",
            "speaker": "",
            "quote": "",
            "date": "",
            "entities": [],
        },
        "quote_verification": {
            "is_quote": False,
            "speaker": "",
            "attribution": "UNVERIFIED",
            "context": "UNKNOWN",
        },
        "date_analysis": {
            "post_date": "",
            "event_date": "",
            "source_dates": [],
            "consistent": True,
            "notes": "",
        },
        "primary_source_found": False,
        "independent_corroboration_count": 0,
        "credible_contradiction_found": False,
        "key_context": [],
        "closest_real_story": None,
    }


def _recommendation(classification: str, verification: dict[str, Any]) -> str:
    """Generate a user recommendation based on the verification result."""
    status = verification.get("status", "")
    if status == "SEARCH_UNAVAILABLE":
        return (
            "Search services were temporarily unavailable. "
            "The claim has not been classified as false. Please try again later."
        )
    if classification == "FAKE":
        return (
            "Do not share this content. Credible evidence contradicts "
            "the central claim in this image."
        )
    if classification == "MISLEADING":
        return (
            "This content may be misleading. Review the cited sources "
            "and context before sharing."
        )
    if classification == "REAL":
        return "This claim appears to be supported by credible reporting."
    if classification == "SATIRE":
        return "This content appears to be satire or parody, not factual news."
    return "Review the cited sources and claim-level context before sharing."


# ---------------------------------------------------------------------------
# Main image scanner
# ---------------------------------------------------------------------------


class PhilippineImageFactChecker:
    """Image-to-text adapter that delegates verification to NewsVerifier.

    Pipeline:
        Image → prepare_image() → ONE Gemini OCR call → clean_ocr_text()
            → NewsVerifier.verify(cleaned_text) → image-aware response wrapper

    This class does NOT independently implement claim extraction, search,
    evidence ranking, adjudication, or verdict logic.  All of those belong
    to the NewsVerifier.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        ocr_engine: PaddleOcrEngine | None = None,
        vision_client: GeminiVisionClient | None = None,
        news_verifier: NewsVerifier | None = None,
    ) -> None:
        self.settings = settings
        self.ocr_engine = ocr_engine or PaddleOcrEngine(settings.paddleocr_language)
        self.vision_client = vision_client or GeminiVisionClient(settings)
        self.news_verifier = news_verifier or NewsVerifier(settings)
        max_concurrent = getattr(settings, "image_max_concurrent_claims", 2)
        self._verification_semaphore = asyncio.Semaphore(max(1, max_concurrent))

    async def aclose(self, *, close_news_verifier: bool = True) -> None:
        close = getattr(self.vision_client, "aclose", None)
        if close is not None:
            await close()
        if close_news_verifier:
            close = getattr(self.news_verifier, "aclose", None)
            if close is not None:
                await close()

    async def _verify_claims(
        self,
        claims: list[str],
        ocr_quality: str = "HIGH",
        uncertain_sections: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Verify multiple claims concurrently bounded by image_max_concurrent_claims."""
        async def _verify_one(claim: str) -> dict[str, Any]:
            async with self._verification_semaphore:
                return await self.news_verifier.verify(claim)

        return await asyncio.gather(*[_verify_one(c) for c in claims])

    async def analyze(self, image_bytes: bytes) -> dict[str, Any]:
        """Analyze an image: extract text via OCR, then verify via NewsVerifier.

        Returns a unified response dict containing OCR metadata, the full
        NewsVerifier result, and timing instrumentation.
        """
        timing: dict[str, float] = {}
        t_total_start = time.perf_counter()

        # --- Step 1: Image preprocessing ---
        t0 = time.perf_counter()
        prepare_options: dict[str, Any] = {"max_pixels": self.settings.image_ocr_max_pixels}
        if hasattr(self.settings, "image_ocr_max_source_pixels"):
            prepare_options["max_source_pixels"] = self.settings.image_ocr_max_source_pixels
        image = await asyncio.to_thread(prepare_image, image_bytes, **prepare_options)
        timing["image_processing_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        # --- Step 2: Gemini Vision OCR (ONE call) with PaddleOCR fallback ---
        ocr_result = await self._extract_text(image, timing)

        # --- Step 3: Check for meaningful text ---
        if not _has_meaningful_text(ocr_result["cleaned_text"]):
            timing["total_ms"] = round((time.perf_counter() - t_total_start) * 1000, 2)
            return _insufficient_text_response(ocr_result, timing)

        # --- Step 4: Delegate to NewsVerifier (the single source of truth) ---
        t0 = time.perf_counter()
        try:
            async with self._verification_semaphore:
                verification = await self.news_verifier.verify(ocr_result["cleaned_text"])
        except Exception:
            logger.warning("NewsVerifier failed for image text", exc_info=True)
            timing["verification_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            timing["total_ms"] = round((time.perf_counter() - t_total_start) * 1000, 2)
            return _verification_error_response(
                ocr_result,
                timing,
                Exception("NewsVerifier call failed"),
            )
        timing["verification_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        timing["total_ms"] = round((time.perf_counter() - t_total_start) * 1000, 2)

        # --- Step 5: Wrap result with image/OCR metadata ---
        response = _build_image_response(ocr_result, verification, timing)
        response["metadata"]["verification_engine"] = type(self.news_verifier).__name__
        return response

    async def _extract_text(
        self,
        image: PreparedImage,
        timing: dict[str, float],
    ) -> dict[str, Any]:
        """Extract text using Gemini Vision OCR, with PaddleOCR as fallback.

        Architecture:
            Gemini OCR → valid usable text? → YES → return
                                             → NO  → PaddleOCR fallback → return
        """
        raw_text = ""
        blocks: list[dict[str, str]] = []
        confidence: float | None = None
        provider = "gemini"
        fallback_used = False

        # --- Primary: Gemini Vision structured OCR ---
        t0 = time.perf_counter()
        gemini_success = False
        if self.vision_client.configured:
            try:
                ocr_data = await self.vision_client.transcribe_structured(image)
                raw_text = ocr_data.get("raw_text", "")
                blocks = ocr_data.get("blocks", [])
                confidence = ocr_data.get("confidence")
                gemini_success = True
            except Exception:
                logger.warning(
                    "Gemini Vision OCR failed; trying PaddleOCR fallback", exc_info=True
                )
        timing["gemini_ocr_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        # --- Fallback: PaddleOCR (only if Gemini failed or returned insufficient text) ---
        gemini_sufficient = gemini_success and _has_meaningful_text(raw_text)
        if not gemini_sufficient:
            t0 = time.perf_counter()
            try:
                segments = await asyncio.to_thread(self.ocr_engine.transcribe, image.processed)
                paddle_text = "\n".join(segment.text for segment in segments)
                if paddle_text.strip():
                    raw_text = paddle_text
                    blocks = [{"text": seg.text, "type": "body"} for seg in segments]
                    paddle_conf, _, _, _ = evaluate_ocr(
                        segments,
                        medium_threshold=self.settings.ocr_medium_confidence,
                        high_threshold=self.settings.ocr_high_confidence,
                    )
                    confidence = round(paddle_conf, 4) if paddle_conf > 0 else None
                    provider = "paddleocr"
                    fallback_used = True
            except OcrUnavailableError:
                logger.warning("PaddleOCR fallback also unavailable", exc_info=True)
            timing["paddleocr_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        # --- Minimal deterministic cleanup ---
        t0 = time.perf_counter()
        headlines = [b["text"] for b in blocks if b.get("type") == "headline"]
        bodies = [b["text"] for b in blocks if b.get("type") == "body"]
        if headlines:
            claim_text = " ".join(headlines)
        elif bodies:
            claim_text = " ".join(bodies)
        elif blocks:
            claim_text = " ".join(
                b["text"] for b in blocks
                if b.get("type") not in {"ui_element", "watermark", "label"}
            )
        else:
            claim_text = raw_text
        cleaned_text = clean_ocr_text(claim_text)
        timing["cleanup_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        return {
            "raw_text": raw_text,
            "cleaned_text": cleaned_text,
            "blocks": blocks,
            "confidence": confidence,
            "provider": provider,
            "fallback_used": fallback_used,
        }
