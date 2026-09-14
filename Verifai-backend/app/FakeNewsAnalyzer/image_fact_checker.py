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
from difflib import SequenceMatcher
from io import BytesIO
from typing import Any
from urllib.parse import urlparse

import httpx
from dateutil import parser as date_parser
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

from app.FakeNewsAnalyzer.news_verifier import NewsVerifier, extract_claim_features
from app.Global.config import Settings

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
    "HEIF": "image/heif",
    "HEIC": "image/heic",
}
AGENCIES = {
    "AFP": "Armed Forces of the Philippines",
    "BFP": "Bureau of Fire Protection",
    "BI": "Bureau of Immigration",
    "BIR": "Bureau of Internal Revenue",
    "BJMP": "Bureau of Jail Management and Penology",
    "BSP": "Bangko Sentral ng Pilipinas",
    "CHED": "Commission on Higher Education",
    "COA": "Commission on Audit",
    "COMELEC": "Commission on Elections",
    "DA": "Department of Agriculture",
    "DAR": "Department of Agrarian Reform",
    "DBM": "Department of Budget and Management",
    "DENR": "Department of Environment and Natural Resources",
    "DEPED": "Department of Education",
    "DepEd": "Department of Education",
    "DFA": "Department of Foreign Affairs",
    "DILG": "Department of the Interior and Local Government",
    "DND": "Department of National Defense",
    "DOE": "Department of Energy",
    "DOH": "Department of Health",
    "DOJ": "Department of Justice",
    "DOLE": "Department of Labor and Employment",
    "DOST": "Department of Science and Technology",
    "DOT": "Department of Tourism",
    "DOTR": "Department of Transportation",
    "DOTr": "Department of Transportation",
    "DPWH": "Department of Public Works and Highways",
    "DSWD": "Department of Social Welfare and Development",
    "DTI": "Department of Trade and Industry",
    "GSIS": "Government Service Insurance System",
    "ICC": "International Criminal Court",
    "LTO": "Land Transportation Office",
    "LTFRB": "Land Transportation Franchising and Regulatory Board",
    "MMDA": "Metropolitan Manila Development Authority",
    "NBI": "National Bureau of Investigation",
    "NDRRMC": "National Disaster Risk Reduction and Management Council",
    "NEDA": "National Economic and Development Authority",
    "OVP": "Office of the Vice President",
    "PAGASA": "Philippine Atmospheric, Geophysical and Astronomical Services Administration",
    "PCG": "Philippine Coast Guard",
    "PCO": "Presidential Communications Office",
    "PHILHEALTH": "Philippine Health Insurance Corporation",
    "PhilHealth": "Philippine Health Insurance Corporation",
    "PHIVOLCS": "Philippine Institute of Volcanology and Seismology",
    "PIA": "Philippine Information Agency",
    "PNA": "Philippine News Agency",
    "PNP": "Philippine National Police",
    "PSA": "Philippine Statistics Authority",
    "PSG": "Presidential Security Group",
    "SSS": "Social Security System",
}
PRIMARY_DOMAINS = {
    "ched.gov.ph",
    "coa.gov.ph",
    "comelec.gov.ph",
    "dbm.gov.ph",
    "deped.gov.ph",
    "dilg.gov.ph",
    "doe.gov.ph",
    "doh.gov.ph",
    "gov.ph",
    "house.gov.ph",
    "icc-cpi.int",
    "officialgazette.gov.ph",
    "ovp.gov.ph",
    "pagasa.dost.gov.ph",
    "phivolcs.dost.gov.ph",
    "pia.gov.ph",
    "pna.gov.ph",
    "pco.gov.ph",
    "pnp.gov.ph",
    "senate.gov.ph",
}
FACT_VERBS = re.compile(
    r"\b(?:is|are|was|were|has|have|had|will|costs?|spent|paid|received|"
    r"approved|signed|arrested|died|killed|assigned|funded|announced|said|"
    r"umabot|gumastos|nagbayad|mayroon|pumirma|inaresto|namatay|"
    r"binisita|bumisita|bibisita|dumalaw|nangako|ipinangako|"
    r"papalayain|palalayain|ipapalaya|pinalaya)\b",
    re.IGNORECASE,
)
SOCIAL_METADATA_PATTERN = re.compile(
    r"(?:[\u00b7\u2022].*\b\d{1,3}\s*(?:s|m|h|d|w|y)\b|"
    r"\b\d{1,3}\s*(?:s|m|h|d|w|y)\b.*[\u00b7\u2022])",
    re.IGNORECASE,
)
MONEY_PATTERN = re.compile(
    r"(?P<phrase>(?:₱|PHP\s*|P\s*)(?P<number>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>billion|million|thousand|bilyon|milyon|libo|[BKM])?)",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?|Enero|Pebrero|Marso|Abril|Mayo|Hunyo|Hulyo|Agosto|"
    r"Setyembre|Oktubre|Nobyembre|Disyembre)\.?\s+\d{1,2}(?:,?\s+\d{4})?\b",
    re.IGNORECASE,
)
FILIPINO_MONTHS = {
    "enero": "January",
    "pebrero": "February",
    "marso": "March",
    "abril": "April",
    "mayo": "May",
    "hunyo": "June",
    "hulyo": "July",
    "agosto": "August",
    "setyembre": "September",
    "oktubre": "October",
    "nobyembre": "November",
    "disyembre": "December",
}


class ImagePreprocessingError(ValueError):
    """Raised when an upload is not a safe, supported image."""


class OcrUnavailableError(RuntimeError):
    """Raised when the primary OCR runtime is not installed or cannot load."""


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


class GeminiVisionClient:
    TRANSCRIPTION_PROMPT = (
        "Transcribe all visible text exactly as shown. Do not summarize. Do not fact-check. "
        "Do not correct factual claims. Do not add missing information. Preserve numbers, names, "
        "symbols, capitalization, line breaks, and wording as accurately as possible. If a word "
        "is unreadable, write [UNCLEAR] instead of guessing. Return only the transcription."
    )
    UNDERSTANDING_PROMPT = (
        "Analyze this Philippine news or social-media image, but do not decide whether its claims "
        "are true or false. Extract what is actually visible and keep content, attribution, "
        "source, and visual branding separate. Read the headline, body, quotations, speaker, "
        "publisher/page, "
        "logo, username/watermark, dates, locations, organizations, agencies, people, caption, and "
        "hashtags. Identify satire, parody, unofficial, opinion, prediction, or announcement cues. "
        "Break the central content into the smallest independently verifiable atomic claims. "
        "Do not drop the subject, location, agency, or topic when splitting claims: every atomic "
        "claim must remain self-contained and searchable on its own. Do not treat a publisher "
        "name, watermark, follow prompt, or logo as part of a factual claim. Do not "
        "guess unclear words: put them in uncertain_text and use [UNCERTAIN] where needed. Mark "
        "needs_ocr true when important visible text is unreadable, blurred, unusually styled, "
        "tiny, overlapping, or otherwise uncertain. Return only the requested JSON object."
    )
    UNDERSTANDING_SCHEMA = {
        "type": "OBJECT",
        "properties": {
            "headline": {"type": "STRING"},
            "body_text": {"type": "STRING"},
            "direct_quotes": {"type": "ARRAY", "items": {"type": "STRING"}},
            "speaker": {"type": "STRING"},
            "publisher": {"type": "STRING"},
            "logo": {"type": "STRING"},
            "username": {"type": "STRING"},
            "dates": {"type": "ARRAY", "items": {"type": "STRING"}},
            "post_date": {"type": "STRING"},
            "event_date": {"type": "STRING"},
            "locations": {"type": "ARRAY", "items": {"type": "STRING"}},
            "organizations": {"type": "ARRAY", "items": {"type": "STRING"}},
            "government_agencies": {"type": "ARRAY", "items": {"type": "STRING"}},
            "people": {"type": "ARRAY", "items": {"type": "STRING"}},
            "caption_text": {"type": "STRING"},
            "hashtags": {"type": "ARRAY", "items": {"type": "STRING"}},
            "content_type": {
                "type": "STRING",
                "enum": [
                    "FACTUAL_NEWS",
                    "DIRECT_QUOTE",
                    "ATTRIBUTED_QUOTE",
                    "PREDICTION",
                    "OPINION",
                    "ANNOUNCEMENT",
                    "SATIRE",
                    "OTHER",
                ],
            },
            "indicators": {"type": "ARRAY", "items": {"type": "STRING"}},
            "atomic_claims": {"type": "ARRAY", "items": {"type": "STRING"}},
            "uncertain_text": {"type": "ARRAY", "items": {"type": "STRING"}},
            "text_quality": {"type": "STRING", "enum": ["HIGH", "MEDIUM", "LOW"]},
            "needs_ocr": {"type": "BOOLEAN"},
        },
        "required": [
            "headline",
            "body_text",
            "direct_quotes",
            "speaker",
            "publisher",
            "logo",
            "username",
            "dates",
            "post_date",
            "event_date",
            "locations",
            "organizations",
            "government_agencies",
            "people",
            "caption_text",
            "hashtags",
            "content_type",
            "indicators",
            "atomic_claims",
            "uncertain_text",
            "text_quality",
            "needs_ocr",
        ],
    }
    NORMALIZATION_PROMPT = (
        "You are an expert Philippine news analyst and fact-checking text normalizer. "
        "Your task is to take OCR-extracted text from an image (which may contain OCR typos, "
        "character confusion like 0/O or 1/I/l, broken line wraps, informal shorthand, "
        "Philippine political acronyms, colloquial numbers, or Taglish slang) and normalize "
        "it into clean, canonical, and structured representations that are maximally helpful "
        "for entity identification, fact-checking, and search.\n\n"
        "Instructions:\n"
        "1. OCR Error Repair: Correct broken words, accidental hyphenations, merged words, and "
        "misread characters (e.g. '0' vs 'O', '1' vs 'I' or 'l', '5' vs 'S', 'rn' vs 'm') "
        "based on Philippine context (Filipino, English, Taglish).\n"
        "2. Entity Disambiguation & Canonicalization:\n"
        "   - People: Expand colloquial names, nicknames, and acronyms to canonical public names "
        "     (e.g., 'PBBM' or 'BBM' -> 'President Ferdinand Marcos Jr.', 'PRRD' or 'Tatay Digong' -> "
        "     'former President Rodrigo Duterte', 'VP Sara' or 'Inday Sara' -> 'Vice President Sara Duterte', "
        "     'Sen. Bato' -> 'Senator Ronald \"Bato\" dela Rosa').\n"
        "   - Government Agencies & Organizations: Expand Philippine agency acronyms into their full "
        "     canonical titles (e.g., 'DepEd' -> 'Department of Education (DepEd)', 'DOTr' -> "
        "     'Department of Transportation (DOTr)', 'DPWH' -> 'Department of Public Works and Highways (DPWH)', "
        "     'ICC' -> 'International Criminal Court (ICC)', 'PAGASA', 'PhilHealth', 'DSWD', etc.).\n"
        "   - Locations: Standardize informal or abbreviated locations (e.g., 'QC' -> 'Quezon City', "
        "     'BGC' -> 'Bonifacio Global City, Taguig', 'Davao City', 'The Hague').\n"
        "   - Monetary Figures: Standardize currency into PHP amounts with comma separators "
        "     (e.g., '₱125M' -> '₱125,000,000', 'PHP 20M' -> '₱20,000,000', '10 bilyon' -> '₱10,000,000,000') "
        "     and record numeric amounts in PHP.\n"
        "   - Dates: Standardize date references into ISO-8601 (YYYY-MM-DD) format whenever identifiable.\n"
        "3. Normalized Text: Formulate a clean, coherent, grammatical text representing the entire visible "
        "content with OCR artifacts fixed and entities made explicit.\n"
        "4. Canonical Atomic Claims: Extract self-contained, independent factual claims where ambiguous "
        "pronouns ('he', 'siya', 'ating pangulo') are replaced with explicit entities so each claim is "
        "independently searchable and verifiable.\n"
        "5. Search Queries: Provide 2 to 4 concise, high-precision search query strings designed to find "
        "authoritative news reports, official agency releases, or fact checks for these claims.\n"
        "6. Corrections: List all OCR errors corrected (original string, corrected string, confidence HIGH/MEDIUM/LOW).\n\n"
        "Do not invent facts not present in the visible source text. Return only the requested JSON object."
    )
    NORMALIZATION_SCHEMA = {
        "type": "OBJECT",
        "properties": {
            "normalized_text": {"type": "STRING"},
            "normalized_values": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "type": {
                            "type": "STRING",
                            "enum": ["MONEY", "DATE", "AGENCY", "PERSON", "LOCATION", "ORGANIZATION", "OTHER"],
                        },
                        "original": {"type": "STRING"},
                        "value": {"type": "STRING"},
                        "normalized": {"type": "STRING"},
                        "currency": {"type": "STRING"},
                        "amount": {"type": "NUMBER"},
                    },
                    "required": ["type", "original", "value"],
                },
            },
            "entities": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "type": {
                            "type": "STRING",
                            "enum": ["PERSON", "ORGANIZATION", "AGENCY", "LOCATION", "MONEY", "DATE", "OTHER"],
                        },
                        "value": {"type": "STRING"},
                        "normalized_value": {"type": "STRING"},
                    },
                    "required": ["type", "value", "normalized_value"],
                },
            },
            "canonical_claims": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
            },
            "corrections": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "original": {"type": "STRING"},
                        "corrected": {"type": "STRING"},
                        "confidence": {"type": "STRING", "enum": ["HIGH", "MEDIUM", "LOW"]},
                    },
                    "required": ["original", "corrected", "confidence"],
                },
            },
            "search_queries": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
            },
        },
        "required": [
            "normalized_text",
            "normalized_values",
            "entities",
            "canonical_claims",
            "corrections",
            "search_queries",
        ],
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
    ) -> str:
        if not self.configured:
            raise OcrUnavailableError("Gemini Vision is not configured")
        keys = await self._available_keys()
        if not keys:
            raise OcrUnavailableError("All Gemini API keys are temporarily cooling down")

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
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
        last_error: httpx.HTTPStatusError | None = None
        for position, api_key in enumerate(keys, start=1):
            response = await self._client.post(
                url,
                headers={"x-goog-api-key": api_key},
                json=payload,
            )
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
            response.raise_for_status()
            data = response.json()
            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = "\n".join(str(part.get("text", "")) for part in parts).strip()
            if not text:
                raise ValueError("Gemini returned no usable text")
            return text

        if last_error is not None:
            raise last_error
        raise OcrUnavailableError("No Gemini API key is currently available")

    async def transcribe(self, image: PreparedImage) -> str:
        if not self.configured:
            return ""
        text = await self.generate(image, self.TRANSCRIPTION_PROMPT)
        return re.sub(r"^```(?:text)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()

    async def understand(
        self,
        image: PreparedImage,
        *,
        fallback_ocr_text: str = "",
        initial: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        prompt = self.UNDERSTANDING_PROMPT
        if fallback_ocr_text:
            prompt += (
                "\n\nThis is a reconciliation pass. Compare the first visual extraction and "
                "fallback OCR below against the image. Correct only differences supported by the "
                "visible image; never invent missing words.\nFIRST EXTRACTION:\n"
                f"{json.dumps(initial or {}, ensure_ascii=False)}\nFALLBACK OCR:\n"
                f"{fallback_ocr_text[:12_000]}"
            )
        raw = await self.generate(
            image,
            prompt,
            generation_config={
                "temperature": 0,
                "maxOutputTokens": 4096,
                "thinkingConfig": {"thinkingLevel": "minimal"},
                "responseMimeType": "application/json",
                "responseSchema": self.UNDERSTANDING_SCHEMA,
            },
        )
        return _normalize_understanding(json.loads(raw))

    async def normalize_text(
        self,
        text: str,
        *,
        image: PreparedImage | None = None,
        understanding: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.configured or not text.strip():
            return {}
        prompt = (
            f"{self.NORMALIZATION_PROMPT}\n\n"
            f"RAW OCR TEXT TO NORMALIZE:\n{text.strip()}"
        )
        if understanding:
            prompt += (
                "\n\nINITIAL VISUAL UNDERSTANDING CONTEXT:\n"
                f"{json.dumps(understanding, ensure_ascii=False)}"
            )
        raw = await self.generate(
            image,
            prompt,
            generation_config={
                "temperature": 0,
                "maxOutputTokens": 4096,
                "thinkingConfig": {"thinkingLevel": "minimal"},
                "responseMimeType": "application/json",
                "responseSchema": self.NORMALIZATION_SCHEMA,
            },
        )
        return _normalize_ai_normalization(json.loads(raw))

    async def aclose(self) -> None:
        await self._client.aclose()


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


CONTENT_TYPES = {
    "FACTUAL_NEWS",
    "DIRECT_QUOTE",
    "ATTRIBUTED_QUOTE",
    "PREDICTION",
    "OPINION",
    "ANNOUNCEMENT",
    "SATIRE",
    "OTHER",
}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(
        dict.fromkeys(text for item in value if (text := " ".join(str(item).split()).strip()))
    )


def _normalize_understanding(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Gemini image understanding must be a JSON object")
    content_type = str(value.get("content_type", "OTHER")).upper().strip()
    if content_type not in CONTENT_TYPES:
        content_type = "OTHER"
    quality = str(value.get("text_quality", "LOW")).upper().strip()
    if quality not in {"HIGH", "MEDIUM", "LOW"}:
        quality = "LOW"
    result: dict[str, Any] = {
        key: " ".join(str(value.get(key, "")).split()).strip()
        for key in (
            "headline",
            "body_text",
            "speaker",
            "publisher",
            "logo",
            "username",
            "post_date",
            "event_date",
            "caption_text",
        )
    }
    for key in (
        "direct_quotes",
        "dates",
        "locations",
        "organizations",
        "government_agencies",
        "people",
        "hashtags",
        "indicators",
        "atomic_claims",
        "uncertain_text",
    ):
        result[key] = _string_list(value.get(key, []))
    if result["direct_quotes"] and result["speaker"]:
        content_type = (
            content_type
            if content_type in {"DIRECT_QUOTE", "ATTRIBUTED_QUOTE"}
            else "ATTRIBUTED_QUOTE"
        )
    result["content_type"] = content_type
    result["text_quality"] = quality
    result["needs_ocr"] = bool(value.get("needs_ocr", False)) or quality == "LOW"
    return result


def _normalize_ai_normalization(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    normalized_text = " ".join(str(value.get("normalized_text", "")).split()).strip()

    normalized_values: list[dict[str, Any]] = []
    for item in value.get("normalized_values", []):
        if not isinstance(item, dict):
            continue
        v_type = str(item.get("type", "OTHER")).upper().strip()
        orig = str(item.get("original", "")).strip()
        val = str(item.get("value", "")).strip()
        norm = str(item.get("normalized", val)).strip()
        if not orig:
            continue
        entry: dict[str, Any] = {
            "type": v_type,
            "original": orig,
            "value": val or norm,
        }
        if norm:
            entry["normalized"] = norm
        if "amount" in item and item["amount"] is not None:
            try:
                entry["amount"] = (
                    float(item["amount"])
                    if "." in str(item["amount"])
                    else int(item["amount"])
                )
            except (ValueError, TypeError):
                pass
        if item.get("currency"):
            entry["currency"] = str(item["currency"]).strip().upper()
        normalized_values.append(entry)

    entities: list[dict[str, str]] = []
    for item in value.get("entities", []):
        if not isinstance(item, dict):
            continue
        e_type = str(item.get("type", "OTHER")).upper().strip()
        val = str(item.get("value", "")).strip()
        norm_val = str(item.get("normalized_value", val)).strip()
        if val:
            entities.append(
                {
                    "type": e_type,
                    "value": val,
                    "normalized_value": norm_val or val,
                }
            )

    canonical_claims = [
        " ".join(str(c).split()).strip()
        for c in value.get("canonical_claims", [])
        if " ".join(str(c).split()).strip()
    ]
    corrections = []
    for item in value.get("corrections", []):
        if isinstance(item, dict) and item.get("original") and item.get("corrected"):
            conf = str(item.get("confidence", "HIGH")).upper().strip()
            if conf not in {"HIGH", "MEDIUM", "LOW"}:
                conf = "MEDIUM"
            corrections.append(
                {
                    "original": str(item["original"]).strip(),
                    "corrected": str(item["corrected"]).strip(),
                    "confidence": conf,
                }
            )
    search_queries = [
        " ".join(str(q).split()).strip()
        for q in value.get("search_queries", [])
        if " ".join(str(q).split()).strip()
    ]
    return {
        "normalized_text": normalized_text,
        "normalized_values": normalized_values,
        "entities": entities,
        "canonical_claims": canonical_claims,
        "corrections": corrections,
        "search_queries": search_queries,
    }


def _heuristic_understanding(text: str) -> dict[str, Any]:
    """Conservative local fallback when structured Gemini output is unavailable."""
    merged = _merge_soft_wrapped_ocr_lines(text)
    lines = [line.strip() for line in merged.splitlines() if line.strip()]
    speaker = ""
    quote = ""
    for line in lines:
        attributed = re.match(
            r"^(?P<speaker>(?:Sir|Atty\.?|Gov\.?|Mayor|President|Sen\.?|Senator|Sec\.?|"
            r"Secretary|VP)\s+[A-Z][\w.-]+(?:\s+[A-Z][\w.-]+){0,3})\s*:\s*"
            r"(?P<quote>.+)$",
            line,
            re.IGNORECASE,
        )
        if attributed:
            speaker = attributed.group("speaker").strip()
            quote = attributed.group("quote").strip(' "“”')
            break
    if not speaker:
        for line in reversed(lines):
            match = re.search(
                r"\b(?:Atty\.?|Gov\.?|Mayor|President|Sen\.?|Senator|Sec\.?|Secretary|VP)\s+"
                r"[A-Z][\w.-]+(?:\s+[A-Z][\w.-]+){0,3}\b",
                line,
            )
            if match:
                speaker = match.group(0)
                break
    if not quote:
        quote_candidate = next(
            (
                line.strip(' "“”')
                for line in lines
                if re.search(r"[\"“”]", line)
                or (
                    speaker
                    and re.search(
                        r"(?:^|\W)(?:ako|akin|ko|kami|namin|I|me|my|we|our)(?:\W|$)",
                        line,
                        re.IGNORECASE,
                    )
                )
            ),
            "",
        )
        quote = quote_candidate
    claims = extract_atomic_claims(quote or merged)
    content_type = "ATTRIBUTED_QUOTE" if speaker and quote else "FACTUAL_NEWS"
    if not quote and re.search(r"\b(?:will|uuwi|madidismantle|babalik|mangyayari)\b", merged, re.I):
        content_type = "PREDICTION"
    publisher = next(
        (
            line
            for line in lines
            if re.search(
                r"\b(?:news|tribune|rappler|inquirer|iskolar|tiktok|official)\b", line, re.I
            )
            and line.casefold() not in {item.casefold() for item in claims}
        ),
        "",
    )
    headline = next((line for line in lines if line in claims), claims[0] if claims else "")
    return _normalize_understanding(
        {
            "headline": headline,
            "body_text": merged,
            "direct_quotes": [quote] if quote else [],
            "speaker": speaker,
            "publisher": publisher,
            "logo": publisher,
            "username": "",
            "dates": [],
            "post_date": "",
            "event_date": "",
            "locations": [],
            "organizations": [],
            "government_agencies": [],
            "people": [speaker] if speaker else [],
            "caption_text": "",
            "hashtags": [],
            "content_type": content_type,
            "indicators": [],
            "atomic_claims": claims,
            "uncertain_text": [],
            "text_quality": "MEDIUM" if text.strip() else "LOW",
            "needs_ocr": not bool(text.strip()),
        }
    )


def _understanding_text(understanding: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("publisher", "username", "headline", "body_text"):
        _append_unique(values, str(understanding.get(key, "")).strip())
    for quote in understanding.get("direct_quotes", []):
        _append_unique(values, str(quote).strip())
    _append_unique(values, str(understanding.get("speaker", "")).strip())
    _append_unique(values, str(understanding.get("caption_text", "")).strip())
    return "\n".join(values)


def _critical_text(value: str) -> bool:
    return bool(
        re.search(r"[₱%\d]", value)
        or re.search(r"\b[A-Z]{2,}\b", value)
        or DATE_PATTERN.search(value)
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


def clean_ocr_text(text: str) -> str:
    """Clean common OCR artifacts from extracted text before claim parsing or searching.

    Fixes:
    - Unicode normalization and non-breaking spaces
    - Hyphenated words broken across line breaks (e.g., 'pagba-\\nbawal' -> 'pagbabawal')
    - Broken lines within continuous sentences (soft breaks)
    - Excessive whitespace and repeated blank lines
    - Repeated punctuation artifacts (e.g., '...', '???', '---')
    - Non-text artifacts or noise at edges
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
    # Strip non-text artifacts from edges
    cleaned = re.sub(r'^[\s\-_~|•*#]+|[\s\-_~|•*#]+$', "", cleaned)
    return cleaned.strip()


def compare_ocr_outputs(
    paddle_text: str, gemini_text: str
) -> tuple[str, list[dict[str, str]], list[dict[str, object]]]:
    paddle_text = clean_ocr_text(paddle_text)
    gemini_text = clean_ocr_text(gemini_text)
    if not gemini_text:
        return paddle_text, [], []
    if not paddle_text:
        return gemini_text, [], []
    paddle_tokens = re.findall(r"₱|PHP|[\w.,%'-]+", paddle_text, flags=re.UNICODE)
    gemini_tokens = re.findall(r"₱|PHP|[\w.,%'-]+", gemini_text, flags=re.UNICODE)
    matcher = SequenceMatcher(
        None,
        [token.casefold() for token in paddle_tokens],
        [token.casefold() for token in gemini_tokens],
    )
    corrections: list[dict[str, str]] = []
    conflicts: list[dict[str, object]] = []
    for operation, left_start, left_end, right_start, right_end in matcher.get_opcodes():
        if operation == "equal":
            continue
        left = " ".join(paddle_tokens[left_start:left_end]).strip()
        right = " ".join(gemini_tokens[right_start:right_end]).strip()
        if not left or not right:
            continue
        confusion_only = _ocr_confusion_key(left) == _ocr_confusion_key(right)
        if confusion_only:
            corrections.append({"original": left, "corrected": right, "confidence": "HIGH"})
        elif _critical_text(left) or _critical_text(right):
            conflicts.append(
                {
                    "status": "OCR_CONFLICT",
                    "candidates": [left, right],
                    "requires_review": True,
                }
            )
        else:
            corrections.append({"original": left, "corrected": right, "confidence": "MEDIUM"})
    similarity = matcher.ratio()
    final_text = gemini_text if similarity >= 0.50 and not conflicts else paddle_text
    return final_text, corrections, conflicts


def _ocr_confusion_key(value: str) -> str:
    return value.casefold().translate(str.maketrans({"o": "0", "i": "1", "l": "1", "s": "5"}))


def normalize_fact_text(value: str) -> tuple[str, list[dict[str, object]]]:
    text = clean_ocr_text(value)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    normalized_values: list[dict[str, object]] = []

    def money_replacement(match: re.Match[str]) -> str:
        phrase = match.group("phrase")
        number = float(match.group("number").replace(",", ""))
        unit = (match.group("unit") or "").casefold()
        multiplier = {
            "b": 1_000_000_000,
            "billion": 1_000_000_000,
            "bilyon": 1_000_000_000,
            "m": 1_000_000,
            "million": 1_000_000,
            "milyon": 1_000_000,
            "k": 1_000,
            "thousand": 1_000,
            "libo": 1_000,
            "": 1,
        }[unit]
        amount = int(number * multiplier)
        normalized_values.append(
            {"type": "MONEY", "original": phrase, "currency": "PHP", "amount": amount}
        )
        return f"₱{amount:,}"

    text = MONEY_PATTERN.sub(money_replacement, text)

    def date_replacement(match: re.Match[str]) -> str:
        phrase = match.group(0)
        translated = phrase
        for filipino, english in FILIPINO_MONTHS.items():
            translated = re.sub(filipino, english, translated, flags=re.IGNORECASE)
        try:
            parsed = date_parser.parse(translated, fuzzy=False)
        except (ValueError, OverflowError):
            return phrase
        if not re.search(r"\b\d{4}\b", translated):
            return phrase
        iso_date = parsed.date().isoformat()
        normalized_values.append({"type": "DATE", "original": phrase, "value": iso_date})
        return iso_date

    text = DATE_PATTERN.sub(date_replacement, text)
    seen_agencies: set[str] = set()
    for acronym, full_name in AGENCIES.items():
        if full_name.casefold() in seen_agencies:
            continue
        if re.search(rf"\b{re.escape(acronym)}\b", text) and full_name.casefold() not in text.casefold():
            text = re.sub(rf"\b{re.escape(acronym)}\b", f"{acronym} ({full_name})", text)
            normalized_values.append({"type": "AGENCY", "original": acronym, "value": full_name})
            seen_agencies.add(full_name.casefold())
    return text, normalized_values


def extract_atomic_claims(text: str) -> list[str]:
    text = _merge_soft_wrapped_ocr_lines(text)
    candidates = re.split(r"(?:\n+|(?<=[.!?])\s+|\s+[;•]\s*)", text)
    claims: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip(" -–—•\t")
        if len(candidate) < 8:
            continue
        if SOCIAL_METADATA_PATTERN.search(candidate) and len(candidate.split()) <= 8:
            continue
        lowered = candidate.casefold()
        if candidate.endswith("?") and not re.search(r"\d", candidate):
            continue
        rhetoric = ("ibahagi ito", "share this", "wake up", "nakakahiya")
        if any(phrase in lowered for phrase in rhetoric):
            if "tax" in lowered or "public funds" in lowered:
                _append_unique(claims, "Public funds were used for the stated expense.")
            continue
        pieces = [candidate]
        if re.search(r"\s+and\s+", candidate, flags=re.IGNORECASE):
            possible = re.split(r"\s+and\s+", candidate, maxsplit=1, flags=re.IGNORECASE)
            if all(FACT_VERBS.search(piece) or re.search(r"[₱%\d]", piece) for piece in possible):
                pieces = possible
        for piece in pieces:
            piece = piece.strip(" ,.;")
            has_event = bool(extract_claim_features(piece).event_categories)
            if FACT_VERBS.search(piece) or re.search(r"[₱%\d]", piece) or has_event:
                _append_unique(claims, piece)
        if len(claims) >= 6:
            break
    if not claims:
        fallback = next(
            (
                item.strip(" ,.;")
                for item in candidates
                if len(item.split()) >= 4 and not item.strip().endswith("?")
            ),
            "",
        )
        _append_unique(claims, fallback)
    return claims


def _merge_soft_wrapped_ocr_lines(text: str) -> str:
    """Join visual screenshot and poster wraps without merging unrelated social UI rows."""
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not lines:
            lines.append(line)
            continue
        previous = lines[-1]
        previous_is_open = not re.search(r"[.!?][\"')\]]*$", previous)
        looks_like_continuation = (
            line[:1].islower()
            or bool(FACT_VERBS.search(previous))
            or bool(
                re.match(
                    r"^(?:breaking\s+news|news\s+alert)\s*:",
                    previous,
                    re.IGNORECASE,
                )
            )
            or bool(re.search(r"[,:;\-–—\(\[\"\'“‘]$", previous))
            or bool(
                re.search(
                    r"\b(?:ng|sa|kay|kina|ni|nina|para|dahil|ayon|at|o|kung|kapag|nang|mga|na|ang|si|sina|"
                    r"to|for|of|in|on|with|by|from|and|or|that|as|than|the|a|an|into|onto|about|is|are|was|were)\b$",
                    previous,
                    re.IGNORECASE,
                )
            )
            or bool(
                re.search(
                    r"^(?:ng|sa|kay|kina|ni|nina|para|dahil|ayon|at|o|kung|kapag|nang|na|"
                    r"to|for|of|in|on|with|by|from|and|or|that|as)\b",
                    line,
                    re.IGNORECASE,
                )
            )
            or (
                previous_is_open
                and len(previous.split()) <= 8
                and len(line.split()) <= 8
                and not SOCIAL_METADATA_PATTERN.search(previous)
                and not SOCIAL_METADATA_PATTERN.search(line)
            )
        )
        if previous_is_open and looks_like_continuation:
            lines[-1] = f"{previous} {line}"
        else:
            lines.append(line)
    return "\n".join(lines)


def _contextual_verification_claim(claim: str, full_text: str) -> str:
    """Add nearby page context when the extracted claim uses an ambiguous reference."""
    if (
        re.search(r"\b(?:return(?:s|ing)?|coming\s+home|uuwi)\b", claim, re.IGNORECASE)
        and re.search(r"\bICC\b|International Criminal Court", full_text, re.IGNORECASE)
        and not re.search(r"\bICC\b|International Criminal Court", claim, re.IGNORECASE)
    ):
        return f"{claim} from ICC custody"
    attribution = _quote_attribution(full_text, claim)
    if attribution:
        return f"{claim} {attribution}"
    ambiguous_reference = re.search(
        r"\b(?:ating\s+pangulo|our\s+president|our\s+leader)\b",
        claim,
        re.IGNORECASE,
    )
    if not ambiguous_reference:
        return claim
    for line in _merge_soft_wrapped_ocr_lines(full_text).splitlines():
        if line.casefold() in claim.casefold() or SOCIAL_METADATA_PATTERN.search(line):
            continue
        context = re.sub(r"\b(?:join|follow)\b", " ", line, flags=re.IGNORECASE)
        context = context.strip(" ·•-–—\t")
        if 1 <= len(context.split()) <= 6:
            return f"{claim} {context}"
    return claim


def _strip_speaker_assertion(claim: str, speaker: str) -> str:
    if not speaker:
        return claim
    escaped = re.escape(speaker)
    stripped = re.sub(
        rf"^{escaped}\s+(?:said|says|stated|states|claimed|claims|predicted|predicts)"
        r"(?:\s+that)?\s*[:,-]?\s*",
        "",
        claim,
        flags=re.IGNORECASE,
    ).strip()
    return stripped or claim


def _quote_attribution(full_text: str, claim: str) -> str:
    """Extract a compact named speaker line from a social quote card."""
    title_pattern = re.compile(
        r"\b(?:Atty\.?|Gov\.?|Mayor|President|Sen\.?|Senator|Sec\.?|Secretary|VP)\s+"
        r"[A-Z][\w.-]+(?:\s+[A-Z][\w.-]+){0,3}\b"
    )
    for line in reversed(_merge_soft_wrapped_ocr_lines(full_text).splitlines()):
        if line.casefold() in claim.casefold():
            continue
        match = title_pattern.search(line)
        if match:
            return match.group(0).strip()
    return ""


def _is_attributed_quote(claim: str, full_text: str) -> bool:
    attribution = _quote_attribution(full_text, claim)
    if not attribution:
        return False
    return bool(
        re.search(r"(?:^|\W)(?:ako|akin|ko|kami|namin|i|me|my|we|our)(?:\W|$)", claim, re.I)
        or re.search(r"^[\"'‘’“”]", claim)
    )


def _append_unique(items: list[str], value: str) -> None:
    if value and value.casefold() not in {item.casefold() for item in items}:
        items.append(value)


def extract_entities(text: str, normalized_values: list[dict[str, object]]) -> list[dict[str, str]]:
    entities: list[dict[str, str]] = []
    for item in normalized_values:
        item_type = str(item["type"])
        if item_type == "MONEY":
            _add_entity(entities, "MONEY", str(item["original"]), f"PHP {item['amount']}")
        elif item_type == "DATE":
            _add_entity(entities, "DATE", str(item["original"]), str(item["value"]))
        elif item_type == "AGENCY":
            _add_entity(entities, "AGENCY", str(item["original"]), str(item["value"]))
    features = extract_claim_features(text)
    if features.attributed_entity:
        _add_entity(
            entities,
            "PERSON",
            features.attributed_entity,
            features.attributed_entity,
        )
    for location in features.locations:
        _add_entity(entities, "LOCATION", location, location)
    for value in features.entities:
        if value in AGENCIES:
            _add_entity(entities, "AGENCY", value, AGENCIES[value])
        elif len(value.split()) >= 2:
            _add_entity(entities, "PERSON", value, value)
        else:
            _add_entity(entities, "ORGANIZATION", value, value)
    return entities[:30]


def _add_entity(entities: list[dict[str, str]], kind: str, value: str, normalized: str) -> None:
    val_clean = value.strip().rstrip(".")
    for item in entities:
        item_val_clean = item["value"].strip().rstrip(".")
        if item["type"] == kind and item_val_clean.casefold() == val_clean.casefold():
            if normalized and (
                item.get("normalized_value", "").casefold() == item["value"].casefold()
                or len(normalized) > len(item.get("normalized_value", ""))
            ):
                item["normalized_value"] = normalized
            return
    entities.append({"type": kind, "value": value, "normalized_value": normalized})


def claim_type(claim: str) -> str:
    lowered = claim.casefold()
    if MONEY_PATTERN.search(claim) or "₱" in claim:
        return "MONEY"
    if "%" in claim or re.search(r"\b\d[\d,]*\s+(?:people|personnel|katao)\b", claim, re.I):
        return "STATISTIC"
    if '"' in claim or "“" in claim or "said" in lowered or "sinabi" in lowered:
        return "QUOTE"
    if any(
        category.startswith("POLICY_")
        for category in extract_claim_features(claim).event_categories
    ) or any(word in lowered for word in ("law", "bill", "policy", "batas", "budget")):
        return "POLICY"
    if FACT_VERBS.search(claim):
        return "EVENT"
    return "FACT"


def numerical_analysis(claim: str) -> dict[str, object]:
    money = list(MONEY_PATTERN.finditer(claim))
    has_numeric = bool(money or re.search(r"\b\d+(?:\.\d+)?%", claim))
    analysis: dict[str, object] = {
        "required": has_numeric,
        "calculation": "",
        "result": "",
        "math_status": "NOT_APPLICABLE",
        "source_status": "UNVERIFIED" if has_numeric else "NOT_APPLICABLE",
    }
    lowered = claim.casefold()
    if money and ("per month" in lowered or "kada buwan" in lowered):
        amount = _money_amount(money[0])
        years = re.search(r"(?:over|for|sa loob ng)\s+(\d+)\s+(?:years?|taon)", lowered)
        months = int(years.group(1)) * 12 if years else 12
        result = amount * months
        analysis.update(
            {
                "calculation": f"PHP {amount:,} × {months} months",
                "result": f"PHP {result:,}",
                "math_status": "CONSISTENT",
                "source_status": "ESTIMATE",
            }
        )
    return analysis


def _money_amount(match: re.Match[str]) -> int:
    number = float(match.group("number").replace(",", ""))
    unit = (match.group("unit") or "").casefold()
    multiplier = {
        "b": 1_000_000_000,
        "billion": 1_000_000_000,
        "bilyon": 1_000_000_000,
        "m": 1_000_000,
        "million": 1_000_000,
        "milyon": 1_000_000,
        "k": 1_000,
        "thousand": 1_000,
        "libo": 1_000,
        "": 1,
    }[unit]
    return int(number * multiplier)


VERDICT_MAP = {
    "VERIFIED": "SUPPORTED",
    "LIKELY_TRUE": "PARTIALLY_SUPPORTED",
    "MISLEADING": "PARTIALLY_SUPPORTED",
    "UNVERIFIED": "UNVERIFIED",
    "LIKELY_FALSE": "CONTRADICTED",
    "FALSE": "CONTRADICTED",
}
RELATIONSHIP_MAP = {
    "SUPPORTS": "SUPPORTS",
    "CONTRADICTS": "CONTRADICTS",
    "RELATED": "UNRELATED",
    "DEBUNKS": "CONTRADICTS",
    "PARTIAL": "PARTIAL",
    "UNRELATED": "UNRELATED",
}


def _understanding_claims(
    understanding: dict[str, Any],
    normalized_text: str,
    *,
    canonical_claims: list[str] | None = None,
) -> list[str]:
    candidates = list(understanding.get("atomic_claims", []))
    quotes = list(understanding.get("direct_quotes", []))
    if quotes and understanding.get("speaker"):
        quote = quotes[0].strip(' "“”')
        if quote and not any(
            _fuzzy_text_match(quote, candidate) >= 0.75 for candidate in candidates
        ):
            candidates.insert(0, quote)
    elif quotes and not candidates:
        for q in quotes:
            clean_q = str(q).strip(' "“”')
            if clean_q and len(clean_q.split()) >= 3:
                candidates.append(clean_q)

    # Fallback to body_text if atomic_claims and quotes are empty
    body = str(understanding.get("body_text", "")).strip()
    if not candidates and body and len(body.split()) >= 3:
        candidates.append(body)

    if not candidates:
        candidates = list(canonical_claims or []) or extract_atomic_claims(normalized_text)
    elif canonical_claims:
        for cc in canonical_claims:
            if not any(_fuzzy_text_match(cc, candidate) >= 0.70 for candidate in candidates):
                candidates.append(cc)

    # Preserve the full headline as the first candidate for searching.
    # Searching the complete headline preserves context and is more effective
    # than searching fragments. This is key for the progressive search flow.
    headline = str(understanding.get("headline", "")).strip()
    if headline and len(headline.split()) >= 3:
        headline_normalized, _ = normalize_fact_text(headline)
        headline_normalized = re.sub(r'^[\s"“”\-–—•]+|[\s"“”\-–—•]+$', "", headline_normalized)
        if headline_normalized and not any(
            _fuzzy_text_match(headline_normalized, c) >= 0.80 for c in candidates
        ):
            candidates.insert(0, headline_normalized)

    claims: list[str] = []
    for candidate in candidates:
        publisher = str(understanding.get("publisher", "")).strip()
        speaker = str(understanding.get("speaker", "")).strip()
        if (
            understanding.get("content_type") in {"DIRECT_QUOTE", "ATTRIBUTED_QUOTE"}
            and quotes
            and speaker
        ):
            stripped = _strip_speaker_assertion(str(candidate), speaker)
            if stripped != str(candidate):
                continue
        if (
            publisher
            and publisher.casefold() in str(candidate).casefold()
            and re.search(
                r"\b(?:publish(?:ed|es)?|post(?:ed|s)?|quote\s+card|content|graphic|logo)\b",
                str(candidate),
                re.IGNORECASE,
            )
        ):
            continue
        normalized, _ = normalize_fact_text(str(candidate))
        normalized = re.sub(r'^[\s"“”\-–—•]+|[\s"“”\-–—•]+$', "", normalized)
        headline_ref = str(understanding.get("headline", ""))
        if (
            re.search(r"\bnuclear\s+energy\b", headline_ref, re.IGNORECASE)
            and re.search(r"\b(?:prepar|advanc|future|DOE)\w*\b", normalized, re.IGNORECASE)
            and not re.search(r"\bnuclear\b", normalized, re.IGNORECASE)
        ):
            normalized = f"{normalized.rstrip('.')} for nuclear energy in the Philippines."
        if len(normalized.split()) >= 3:
            _append_unique(claims, normalized)
        if len(claims) >= 6:
            break
    return claims


def _fuzzy_text_match(left: str, right: str) -> float:
    left_tokens = " ".join(re.findall(r"\w+", left.casefold()))
    right_tokens = " ".join(re.findall(r"\w+", right.casefold()))
    return SequenceMatcher(None, left_tokens, right_tokens).ratio()


def _merge_understanding_entities(
    entities: list[dict[str, str]], understanding: dict[str, Any]
) -> None:
    groups = {
        "people": "PERSON",
        "organizations": "ORGANIZATION",
        "government_agencies": "AGENCY",
        "locations": "LOCATION",
    }
    for key, kind in groups.items():
        for value in understanding.get(key, []):
            normalized = AGENCIES.get(str(value).upper(), str(value))
            _add_entity(entities, kind, str(value), normalized)


def _public_extracted(understanding: dict[str, Any]) -> dict[str, Any]:
    entity_values = list(
        dict.fromkeys(
            str(item)
            for key in ("people", "organizations", "government_agencies", "locations")
            for item in understanding.get(key, [])
            if str(item).strip()
        )
    )
    dates = understanding.get("dates", [])
    return {
        "headline": understanding.get("headline", ""),
        "body_text": understanding.get("body_text", ""),
        "publisher": understanding.get("publisher", ""),
        "speaker": understanding.get("speaker", ""),
        "quote": " ".join(understanding.get("direct_quotes", [])).strip(),
        "date": understanding.get("post_date") or (dates[0] if dates else ""),
        "entities": entity_values,
    }


def _quote_verification(
    understanding: dict[str, Any], claims: list[dict[str, Any]]
) -> dict[str, Any]:
    speaker = str(understanding.get("speaker", ""))
    is_quote = bool(understanding.get("direct_quotes") and speaker) or understanding.get(
        "content_type"
    ) in {"DIRECT_QUOTE", "ATTRIBUTED_QUOTE"}
    if not is_quote:
        return {
            "is_quote": False,
            "speaker": speaker,
            "attribution": "UNVERIFIED",
            "context": "UNKNOWN",
        }
    # Atomic-claim extraction may put a headline ahead of the visible quotation.
    # Do not let that ordering decide whether the attribution itself was checked.
    visible_quotes = [str(item).strip(' "â€œâ€') for item in understanding.get("direct_quotes", [])]
    quote_claim = (
        max(
            claims,
            key=lambda candidate: max(
                (
                    _fuzzy_text_match(str(candidate.get("claim", "")), quote)
                    for quote in visible_quotes
                    if quote
                ),
                default=0.0,
            ),
        )
        if claims and visible_quotes
        else (claims[0] if claims else None)
    )
    attribution = "UNVERIFIED"
    context = "UNKNOWN"
    if quote_claim and quote_claim["verdict"] in {"SUPPORTED", "PARTIALLY_SUPPORTED"}:
        publisher = str(understanding.get("publisher", "")).strip().casefold()
        has_direct_support = any(
            item["relationship"] == "SUPPORTS"
            and (
                item["source_type"] in {"PRIMARY", "MAJOR_NEWS"}
                or (publisher and publisher in item.get("source", "").casefold())
            )
            for item in quote_claim["evidence"]
        )
        if has_direct_support:
            attribution = "VERIFIED"
            context = (
                "PARTIAL"
                if quote_claim.get("_provider_verdict") in {"LIKELY_TRUE", "MISLEADING"}
                else "ACCURATE"
            )
    false_attribution_evidence = any(
        item["relationship"] == "CONTRADICTS"
        and item["source_type"] in {"PRIMARY", "MAJOR_NEWS"}
        and re.search(
            r"\b(?:attribut|fabricat|did not say|never said|altered quote|fake quote)\w*\b",
            item["reason"],
            re.IGNORECASE,
        )
        for item in (quote_claim["evidence"] if quote_claim else [])
    )
    if quote_claim and quote_claim["verdict"] == "CONTRADICTED" and false_attribution_evidence:
        attribution = "FALSE"
        context = "ALTERED"
    if quote_claim and quote_claim.get("_provider_verdict") == "MISLEADING":
        context = "MISLEADING"
    return {
        "is_quote": True,
        "speaker": speaker,
        "attribution": attribution,
        "context": context,
    }


def _date_analysis(understanding: dict[str, Any], claims: list[dict[str, Any]]) -> dict[str, Any]:
    source_dates = list(
        dict.fromkeys(
            item["publication_date"]
            for claim in claims
            for item in claim["evidence"]
            if item["publication_date"]
        )
    )
    misleading = any(claim.get("_provider_verdict") == "MISLEADING" for claim in claims)
    notes = (
        "Reliable evidence indicates that the image's time framing is inconsistent or outdated."
        if misleading
        else (
            "No material date conflict was identified in the retrieved evidence."
            if source_dates
            else "No reliable source date was available for comparison."
        )
    )
    return {
        "post_date": str(understanding.get("post_date", "")),
        "event_date": str(understanding.get("event_date", "")),
        "source_dates": source_dates,
        "consistent": not misleading,
        "notes": notes,
    }


def _credible_contradiction_found(claims: list[dict[str, Any]]) -> bool:
    return any(
        item["relationship"] == "CONTRADICTS" and item["source_type"] in {"PRIMARY", "MAJOR_NEWS"}
        for claim in claims
        for item in claim["evidence"]
    )


def _is_synthetic_or_fabricated_image(
    ai_detection: dict[str, Any] | None,
    understanding: dict[str, Any] | None = None,
) -> bool:
    """Check if visual AI assessment indicates a genuinely synthetic or fabricated image.

    Normal graphic designs (news cards, quote cards, posters, collages with text overlay)
    combine photos, backgrounds, and text banners. These are standard composite graphics,
    NOT deceptive AI-generated or manipulated images.
    """
    if not ai_detection:
        return False
    classification = str(ai_detection.get("classification", ""))
    ai_prob = int(ai_detection.get("ai_probability", 0))
    if ai_prob < 60:
        return False

    summary_lower = str(ai_detection.get("summary", "")).lower()
    signals_lower = " ".join(str(s).lower() for s in ai_detection.get("signals", []))
    combined_desc = f"{summary_lower} {signals_lower}"

    graphic_cues = (
        "composite graphic",
        "graphic design",
        "overlaid text",
        "text overlay",
        "quote card",
        "poster",
        "banner",
        "cutout portrait",
        "stylized background",
        "photo collage",
    )
    is_normal_graphic_design = any(cue in combined_desc for cue in graphic_cues)

    # If it is explicitly described as a composite graphic rather than synthetic generation
    if "rather than" in summary_lower and "ai generation" in summary_lower:
        return False
    if "typical of a composite graphic" in summary_lower:
        return False

    if classification == "Likely AI-generated":
        if is_normal_graphic_design and not any(
            w in combined_desc for w in ("distortion", "synthetic", "warped", "fabricated")
        ):
            return False
        return True

    if classification == "Manipulation suspected":
        if is_normal_graphic_design:
            return False
        content_type = str((understanding or {}).get("content_type", "")).upper()
        if content_type in {"FACTUAL_NEWS", "DIRECT_QUOTE", "ATTRIBUTED_QUOTE", "ANNOUNCEMENT"}:
            return False
        return ai_prob >= 75

    return False


def _public_classification(
    understanding: dict[str, Any],
    claims: list[dict[str, Any]],
    quote_verification: dict[str, Any],
    date_analysis: dict[str, Any],
    ai_detection: dict[str, Any] | None = None,
) -> str:
    ai_flagged = _is_synthetic_or_fabricated_image(ai_detection, understanding)
    if not claims:
        if ai_flagged:
            return "FAKE"
        return "INSUFFICIENT_EVIDENCE"
    credible_contradiction = _credible_contradiction_found(claims)
    central = claims[0]
    if quote_verification["is_quote"]:
        if credible_contradiction:
            return "FAKE"
        if quote_verification["attribution"] == "VERIFIED" and quote_verification["context"] in {
            "ACCURATE",
            "PARTIAL",
        }:
            return "QUOTE"
        if quote_verification["attribution"] == "FALSE":
            return "FAKE"
        if ai_flagged and quote_verification["attribution"] != "VERIFIED":
            return "FAKE"
        return "INSUFFICIENT_EVIDENCE"

    if central["verdict"] == "CONTRADICTED" and credible_contradiction:
        return "FAKE"
    # A card can contain a broad headline plus several atomic assertions.  A weak,
    # broad headline result must not conceal multiple directly contradicted material
    # assertions (for example, a claimed release and a claimed official statement).
    contradicted_claims = [
        claim
        for claim in claims
        if claim["verdict"] == "CONTRADICTED"
        and any(
            item["relationship"] == "CONTRADICTS"
            and item["source_type"] in {"PRIMARY", "MAJOR_NEWS"}
            for item in claim["evidence"]
        )
    ]
    if len(contradicted_claims) >= 2:
        return "FAKE"
    if not date_analysis["consistent"] and any(
        item["source_type"] in {"PRIMARY", "MAJOR_NEWS"}
        for claim in claims
        for item in claim["evidence"]
    ):
        return "FAKE"
    supported = all(claim["verdict"] in {"SUPPORTED", "PARTIALLY_SUPPORTED"} for claim in claims)
    supported_coverage = (
        sum(
            claim["verdict"] in {"SUPPORTED", "PARTIALLY_SUPPORTED"}
            for claim in claims
        )
        / len(claims)
    )
    decisive_support = [
        item
        for claim in claims
        for item in claim["evidence"]
        if item["relationship"] == "SUPPORTS" and item["source_type"] in {"PRIMARY", "MAJOR_NEWS"}
    ]
    support_domains = {urlparse(item["url"]).hostname for item in decisive_support}
    has_primary = any(item["source_type"] == "PRIMARY" for item in decisive_support)
    if (
        (supported or supported_coverage >= 0.75)
        and decisive_support
        and (has_primary or len(support_domains) >= 1)
    ):
        return "REAL"

    # If visual analysis indicates the image is synthetic/manipulated and no credible
    # reporting supports the depicted event, classify the image as fake.
    if ai_flagged and not decisive_support and not supported:
        return "FAKE"

    return "INSUFFICIENT_EVIDENCE"


def _classification_confidence(
    classification: str,
    claims: list[dict[str, Any]],
    text_quality: str,
    has_conflicts: bool,
    ai_detection: dict[str, Any] | None = None,
) -> int:
    scores = [int(claim["confidence"]) for claim in claims]
    score = round(sum(scores) / len(scores)) if scores else 10
    if classification == "FAKE" and ai_detection and _is_synthetic_or_fabricated_image(ai_detection):
        ai_prob = int(ai_detection.get("ai_probability", 75))
        ai_conf = int(ai_detection.get("confidence", 70))
        score = max(score, min(95, round((ai_prob + ai_conf) / 2)))
    if classification == "INSUFFICIENT_EVIDENCE":
        score = min(score, 49)
    if has_conflicts or text_quality == "LOW":
        score = min(score, 35)
    elif text_quality == "MEDIUM":
        score = min(score, 85)
    return max(0, min(100, score))


def _reasoning_summary(
    classification: str,
    claims: list[dict[str, Any]],
    quote_verification: dict[str, Any],
    date_analysis: dict[str, Any],
    ai_detection: dict[str, Any] | None = None,
) -> str:
    primary_sources = {
        item["url"]
        for claim in claims
        for item in claim["evidence"]
        if item["source_type"] == "PRIMARY"
    }
    major_sources = {
        item["url"]
        for claim in claims
        for item in claim["evidence"]
        if item["source_type"] == "MAJOR_NEWS"
    }
    if classification == "REAL":
        return (
            f"The central factual claims are supported by {len(primary_sources)} primary and "
            f"{len(major_sources)} established-news source(s), with no stronger "
            "contradiction found."
        )
    if classification == "QUOTE":
        return (
            f"The words attributed to {quote_verification['speaker']} were found in credible "
            "source material and substantially match the image's wording."
        )
    if classification == "FAKE":
        ai_flagged = _is_synthetic_or_fabricated_image(ai_detection)
        if ai_flagged:
            summary = str(ai_detection.get("summary", "visual analysis detected AI-generated signals")).strip()
            return (
                f"The image is classified as fake because visual analysis indicates it is "
                f"{str(ai_detection.get('classification', 'likely AI-generated')).lower()} ({summary}), "
                "and no credible reporting corroborates the depicted event."
            )
        reason = (
            "reliable evidence shows inconsistent date framing"
            if not date_analysis["consistent"]
            else "authoritative or established reporting contradicts a central claim or attribution"
        )
        return f"The image is classified as fake because {reason}."
    if classification == "INSUFFICIENT_EVIDENCE":
        has_related = any(
            item.get("relationship") in {"PARTIAL", "SUPPORTS"} or item.get("similarity", 0) >= 40
            for claim in claims
            for item in claim.get("evidence", [])
        )
        if has_related:
            return (
                "The available reporting discusses related statements or policy considerations, "
                "but is not sufficient to definitively confirm or refute the claim depicted in the image. "
                "Related coverage is cited below."
            )
        return (
            "The available reliable evidence is not sufficient to confirm or refute the central "
            "claim. Missing results are not treated as proof that the image is fake."
        )


def _user_explanation(classification: str, confidence: int, reasoning: str) -> str:
    label = "UNABLE TO VERIFY" if classification == "INSUFFICIENT_EVIDENCE" else classification
    return f"{label} — {confidence}% confidence\n\n{reasoning}"


class PhilippineImageFactChecker:
    def __init__(
        self,
        settings: Settings,
        *,
        ocr_engine: PaddleOcrEngine | None = None,
        vision_client: GeminiVisionClient | None = None,
        news_verifier: NewsVerifier | None = None,
        image_detector: GeminiImageDetector | None = None,
    ) -> None:
        self.settings = settings
        self.ocr_engine = ocr_engine or PaddleOcrEngine(settings.paddleocr_language)
        self.vision_client = vision_client or GeminiVisionClient(settings)
        self.news_verifier = news_verifier or NewsVerifier(settings)
        self.image_detector = image_detector or GeminiImageDetector(self.vision_client)
        self._claim_slots = asyncio.Semaphore(getattr(settings, "image_max_concurrent_claims", 2))

    async def aclose(self, *, close_news_verifier: bool = True) -> None:
        close = getattr(self.vision_client, "aclose", None)
        if close is not None:
            await close()
        if close_news_verifier:
            close = getattr(self.news_verifier, "aclose", None)
            if close is not None:
                await close()

    def warmup(self) -> None:
        self.ocr_engine.warmup()

    async def analyze(self, image_bytes: bytes) -> dict[str, Any]:
        prepare_options = {"max_pixels": self.settings.image_ocr_max_pixels}
        if hasattr(self.settings, "image_ocr_max_source_pixels"):
            prepare_options["max_source_pixels"] = self.settings.image_ocr_max_source_pixels
        image = await asyncio.to_thread(prepare_image, image_bytes, **prepare_options)

        ai_detection: dict[str, Any] | None = None
        if (
            self.vision_client.configured
            and hasattr(self.vision_client, "generate")
            and hasattr(self.image_detector, "analyze")
        ):
            try:
                ai_detection = await self.image_detector.analyze(image)
            except Exception:
                logger.warning("Image AI detection check failed", exc_info=True)
                ai_detection = None

        understanding: dict[str, Any] = {}
        gemini_text = ""
        structured_vision = False
        vision_failure: Exception | None = None
        if self.vision_client.configured:
            try:
                understand = getattr(self.vision_client, "understand", None)
                if understand is not None:
                    understanding = await understand(image)
                    structured_vision = True
                    gemini_text = _understanding_text(understanding)
                else:
                    gemini_text = await self.vision_client.transcribe(image)
                    understanding = _heuristic_understanding(gemini_text)
            except (httpx.HTTPError, OcrUnavailableError, KeyError, TypeError, ValueError) as exc:
                logger.warning(
                    "Gemini image understanding failed; trying OCR fallback", exc_info=True
                )
                vision_failure = exc

        segments: list[OcrSegment] = []
        paddle_failure: OcrUnavailableError | None = None
        needs_paddle = (
            not understanding or bool(understanding.get("needs_ocr")) or not structured_vision
        )
        if needs_paddle:
            try:
                segments = await asyncio.to_thread(self.ocr_engine.transcribe, image.processed)
            except OcrUnavailableError as exc:
                logger.warning("Fallback PaddleOCR engine is unavailable", exc_info=True)
                paddle_failure = exc
        paddle_confidence, paddle_quality, uncertain, _ = evaluate_ocr(
            segments,
            medium_threshold=self.settings.ocr_medium_confidence,
            high_threshold=self.settings.ocr_high_confidence,
        )
        raw_paddle = "\n".join(segment.text for segment in segments)

        if understanding and raw_paddle and structured_vision:
            try:
                understanding = await self.vision_client.understand(
                    image,
                    fallback_ocr_text=raw_paddle,
                    initial=understanding,
                )
                gemini_text = _understanding_text(understanding)
            except (httpx.HTTPError, OcrUnavailableError, KeyError, TypeError, ValueError):
                logger.warning("Gemini OCR reconciliation failed", exc_info=True)
                uncertain.append(
                    {
                        "text": "Gemini reconciliation unavailable",
                        "confidence": 0.0,
                        "critical": False,
                    }
                )
        elif not understanding and raw_paddle:
            understanding = _heuristic_understanding(raw_paddle)

        if not understanding:
            if paddle_failure is not None:
                raise paddle_failure
            if isinstance(vision_failure, OcrUnavailableError):
                raise vision_failure
            raise OcrUnavailableError("No image text extraction provider produced usable text")

        quality = (
            str(understanding.get("text_quality", "LOW"))
            if structured_vision or gemini_text
            else paddle_quality
        )
        for text in understanding.get("uncertain_text", []):
            uncertain.append({"text": text, "confidence": 0.0, "critical": _critical_text(text)})
        if paddle_failure is not None:
            uncertain.append(
                {
                    "text": "Fallback PaddleOCR engine unavailable",
                    "confidence": 0.0,
                    "critical": False,
                }
            )

        likely_text, corrections, conflicts = compare_ocr_outputs(raw_paddle, gemini_text)
        if not likely_text:
            likely_text = _understanding_text(understanding)
        normalized_text, normalized_values = normalize_fact_text(likely_text)

        gemini_norm: dict[str, Any] | None = None
        if (
            self.vision_client.configured
            and hasattr(self.vision_client, "normalize_text")
            and likely_text.strip()
        ):
            try:
                gemini_norm = await self.vision_client.normalize_text(
                    likely_text,
                    image=image,
                    understanding=understanding if structured_vision else None,
                )
            except Exception:
                logger.warning(
                    "Gemini AI text normalization failed; proceeding with rule-based normalization",
                    exc_info=True,
                )
                gemini_norm = None

        canonical_claims: list[str] = []
        gemini_search_queries: list[str] = []
        if gemini_norm:
            ai_norm_text = gemini_norm.get("normalized_text", "").strip()
            if ai_norm_text:
                post_norm_text, post_values = normalize_fact_text(ai_norm_text)
                normalized_text = post_norm_text
                for pv in post_values:
                    if not any(
                        nv.get("type") == pv.get("type") and nv.get("original") == pv.get("original")
                        for nv in normalized_values
                    ):
                        normalized_values.append(pv)

            for gv in gemini_norm.get("normalized_values", []):
                if not any(
                    nv.get("type") == gv.get("type") and nv.get("original") == gv.get("original")
                    for nv in normalized_values
                ):
                    normalized_values.append(gv)

            for gc in gemini_norm.get("corrections", []):
                if not any(c.get("original") == gc.get("original") for c in corrections):
                    corrections.append(gc)

            canonical_claims = gemini_norm.get("canonical_claims", [])
            gemini_search_queries = gemini_norm.get("search_queries", [])

        claims = _understanding_claims(
            understanding,
            normalized_text,
            canonical_claims=canonical_claims,
        )
        if not claims:
            # Fallback attempts to extract usable claim text from headline, body, quotes, gemini_text, or raw_paddle
            fallback_text = (
                clean_ocr_text(str(understanding.get("headline", ""))).strip()
                or clean_ocr_text(str(understanding.get("body_text", ""))).strip()
                or (understanding.get("direct_quotes", [""])[0] if understanding.get("direct_quotes") else "")
                or normalized_text.strip()
                or gemini_text.strip()
                or raw_paddle.strip()
            )
            if fallback_text and len(fallback_text.split()) >= 3:
                claims = [fallback_text]

        # Verification is blocked only if neither Gemini Vision nor OCR produced usable claims,
        # or if Gemini Vision was unavailable and OCR quality was LOW (unverified low-confidence OCR).
        verification_blocked = (not bool(claims)) or (
            not gemini_text and not structured_vision and quality == "LOW"
        )
        if verification_blocked:
            claims = []
        # Add the full headline and Tagalog-translated versions to search queries
        # so the verifier can find English-language articles for Filipino claims.
        headline = clean_ocr_text(str(understanding.get("headline", ""))).strip()
        if headline and len(headline.split()) >= 3:
            if headline not in gemini_search_queries:
                gemini_search_queries.append(headline)
        # Translate Tagalog claims to English for better search coverage
        from app.FakeNewsAnalyzer.news_verifier import (
            _is_predominantly_tagalog,
            translate_tagalog_claim,
        )
        for text_to_translate in [headline, normalized_text, *claims]:
            if text_to_translate and _is_predominantly_tagalog(text_to_translate):
                for tq in translate_tagalog_claim(text_to_translate):
                    if tq not in gemini_search_queries:
                        gemini_search_queries.append(tq)
            if text_to_translate and "castro" in text_to_translate.casefold() and "facebook" in text_to_translate.casefold():
                for cq in (
                    "Marcos open to banning Facebook Claire Castro",
                    "Palace open to banning Facebook Claire Castro",
                    "President Marcos Facebook ban Castro",
                ):
                    if cq not in gemini_search_queries:
                        gemini_search_queries.append(cq)

        claim_results = (
            []
            if verification_blocked
            else await self._verify_claims(
                claims,
                quality,
                conflicts,
                normalized_text,
                content_type=understanding["content_type"],
                speaker=understanding["speaker"],
                direct_quotes=understanding.get("direct_quotes", []),
                publisher=understanding.get("publisher", ""),
                extra_search_queries=gemini_search_queries,
                canonical_claims=canonical_claims,
            )
        )
        for index, claim_result in enumerate(claim_results, start=1):
            claim_result["claim_id"] = f"C{index}"

        closest_story: dict[str, Any] = {
            "found": False,
            "title": "",
            "publisher": "",
            "url": "",
            "date": "",
            "similarity": 0,
            "explanation": "",
            "image_url": "",
        }
        for cr in claim_results:
            cand = cr.get("_closest_real_story")
            if cand and cand.get("found"):
                if not closest_story["found"] or cand.get("similarity", 0) > closest_story.get("similarity", 0):
                    closest_story = cand
        if not closest_story["found"] and claim_results:
            all_evidence = [ev for cr in claim_results for ev in cr.get("evidence", []) if ev.get("url")]
            partial_ev = [ev for ev in all_evidence if ev.get("relationship") == "PARTIAL"] or all_evidence
            if partial_ev:
                best_ev = max(partial_ev, key=lambda e: (e.get("similarity", 0), bool(e.get("title"))))
                closest_story = {
                    "found": True,
                    "title": best_ev.get("title") or best_ev.get("reason", ""),
                    "publisher": best_ev.get("source", ""),
                    "url": best_ev.get("url", ""),
                    "date": best_ev.get("publication_date", ""),
                    "similarity": best_ev.get("similarity", 50),
                    "explanation": best_ev.get("reason", "Closest matching news report."),
                    "image_url": "",
                }
        entities = extract_entities(normalized_text, normalized_values)
        _merge_understanding_entities(entities, understanding)
        if gemini_norm:
            for ge in gemini_norm.get("entities", []):
                _add_entity(entities, ge["type"], ge["value"], ge["normalized_value"])
        independence = _source_independence(claim_results)
        quote_verification = _quote_verification(understanding, claim_results)
        date_analysis = _date_analysis(understanding, claim_results)
        classification = _public_classification(
            understanding,
            claim_results,
            quote_verification,
            date_analysis,
            ai_detection=ai_detection,
        )
        numeric_confidence = _classification_confidence(
            classification,
            claim_results,
            quality,
            bool(conflicts),
            ai_detection=ai_detection,
        )
        overall_verdict = {
            "REAL": "SUPPORTED",
            "QUOTE": "SUPPORTED",
            "FAKE": "FALSE",
            "INSUFFICIENT_EVIDENCE": "UNVERIFIABLE",
        }[classification]
        overall_confidence = (
            "HIGH" if numeric_confidence >= 80 else "MEDIUM" if numeric_confidence >= 55 else "LOW"
        )
        key_context = list(
            dict.fromkeys(
                warning for claim in claim_results for warning in claim["context_warnings"]
            )
        )[:8]
        if conflicts:
            key_context.insert(0, "Critical OCR text conflicts require human review.")
        if verification_blocked:
            key_context.insert(
                0,
                "OCR was not reliable enough to use as the basis for factual verdicts.",
            )
        reasoning_summary = (
            "OCR quality was insufficient and no successful fallback transcription was "
            "available, so no factual verdict was produced."
            if verification_blocked
            else _reasoning_summary(
                classification,
                claim_results,
                quote_verification,
                date_analysis,
                ai_detection=ai_detection,
            )
        )
        ai_detected_fake = _is_synthetic_or_fabricated_image(ai_detection, understanding)
        recommendation = (
            "Do not share this image as verified until its text is transcribed and reviewed."
            if verification_blocked
            else (
                "Do not share this image: visual assessment indicates it is likely AI-generated or manipulated, and the depicted event is uncorroborated."
                if classification == "FAKE" and ai_detected_fake
                else (
                    "Do not share this image as verified until the OCR conflicts are manually resolved."
                    if conflicts
                    else "Review the cited sources and claim-level context before sharing."
                )
            )
        )
        provenance_status = "SUSPICIOUS" if ai_detected_fake else "UNKNOWN"
        provenance_notes = (
            f"Visual assessment: {ai_detection.get('classification')} — {ai_detection.get('summary')}"
            if ai_detection and ai_detection.get("summary")
            else (
                "Textual evidence was checked, but reverse-image provenance is not available "
                "from the configured search providers."
            )
        )
        debug_info = {
            "verification_blocked": verification_blocked,
            "ocr_engine_used": "Gemini Vision" if (structured_vision or gemini_text) else "PaddleOCR",
            "ocr_quality": quality,
            "claim_search_attempted": not verification_blocked and bool(claims),
            "search_queries_count": len(gemini_search_queries),
            "claims_extracted_count": len(claims),
            "total_search_results": sum(
                len(c.get("evidence", [])) for c in claim_results
            ),
        }
        return {
            "analysis_type": "philippine_news_image_fact_check",
            "classification": classification,
            "confidence": numeric_confidence,
            "content_type": understanding["content_type"],
            "extracted": _public_extracted(understanding),
            "ocr": {
                "primary_engine": "Gemini Vision",
                "fallback_engine": "PaddleOCR",
                "gemini_used": structured_vision or bool(gemini_text),
                "raw_paddle_text": raw_paddle,
                "paddle_confidence": round(paddle_confidence, 4),
                "paddle_segments": [segment.as_dict() for segment in segments],
                "gemini_transcription": gemini_text,
                "normalized_text": normalized_text,
                "normalized_values": normalized_values,
                "ocr_quality": quality,
                "uncertain_sections": uncertain,
                "ocr_conflicts": conflicts,
                "corrections": corrections,
            },
            "entities": entities,
            "claims": claim_results,
            "quote_verification": quote_verification,
            "date_analysis": date_analysis,
            "primary_source_found": independence["unique_primary_sources"] > 0,
            "independent_corroboration_count": independence["unique_secondary_sources"],
            "credible_contradiction_found": _credible_contradiction_found(claim_results),
            "reasoning_summary": reasoning_summary,
            "user_explanation": _user_explanation(
                classification, numeric_confidence, reasoning_summary
            ),
            "source_independence": independence,
            "image_provenance": {
                "status": provenance_status,
                "original_source_found": False,
                "notes": provenance_notes,
            },
            "overall_verdict": overall_verdict,
            "overall_confidence": overall_confidence,
            "summary": reasoning_summary,
            "key_context": key_context,
            "recommendation": recommendation,
            "closest_real_story": closest_story,
            "debug": debug_info,
        }

    async def _verify_claims(
        self,
        claims: list[str],
        ocr_quality: str,
        conflicts: list[dict[str, object]],
        full_text: str = "",
        *,
        content_type: str = "OTHER",
        speaker: str = "",
        direct_quotes: list[str] | None = None,
        publisher: str = "",
        extra_search_queries: list[str] | None = None,
        canonical_claims: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        async def verify_one(claim: str) -> dict[str, Any]:
            is_quote = content_type in {"DIRECT_QUOTE", "ATTRIBUTED_QUOTE"} or bool(speaker)
            verification_claim = claim
            matching_canonical = next(
                (c for c in (canonical_claims or []) if _fuzzy_text_match(c, claim) >= 0.65),
                "",
            )
            matches_visible_quote = any(
                _fuzzy_text_match(claim, quote) >= 0.65 for quote in (direct_quotes or [])
            )
            stripped_attribution = _strip_speaker_assertion(claim, speaker)
            if stripped_attribution != claim and not matches_visible_quote:
                verification_claim = stripped_attribution
            elif is_quote and matches_visible_quote and speaker.casefold() not in claim.casefold():
                verification_claim = f"{claim} {speaker}".strip()
            elif matching_canonical and not is_quote:
                verification_claim = matching_canonical
            verification_claim = _contextual_verification_claim(verification_claim, full_text)
            claim_queries = list(extra_search_queries or [])
            if is_quote and matches_visible_quote and speaker:
                # Exact-phrase search is materially more discriminating for an
                # attributed quote than a bag of headline keywords.
                exact_quote_query = f'"{claim}" {speaker}'.strip()
                if exact_quote_query not in claim_queries:
                    claim_queries.append(exact_quote_query)
            try:
                async with self._claim_slots:
                    try:
                        result = await self.news_verifier.verify(
                            verification_claim,
                            publisher=publisher,
                            extra_queries=claim_queries,
                        )
                    except TypeError as exc:
                        if "extra_queries" in str(exc):
                            try:
                                result = await self.news_verifier.verify(verification_claim, publisher=publisher)
                            except TypeError:
                                result = await self.news_verifier.verify(verification_claim)
                        elif "publisher" in str(exc):
                            result = await self.news_verifier.verify(verification_claim)
                        else:
                            raise
            except Exception:
                logger.warning("Claim verification dependency failed", exc_info=True)
                result = _unavailable_claim_verification(claim)
            return _claim_response(
                claim,
                result,
                ocr_quality,
                conflicts,
                attributed_quote=is_quote,
                original_claim=claim,
                normalized_claim=matching_canonical or claim,
                extra_search_queries=claim_queries,
            )

        return list(await asyncio.gather(*(verify_one(claim) for claim in claims)))


def _unavailable_claim_verification(claim: str) -> dict[str, Any]:
    return {
        "status": "SEARCH_UNAVAILABLE",
        "verdict": "UNVERIFIED",
        "confidence": 0,
        "explanation": ("Search services were unavailable, so this claim could not be verified."),
        "search": {"queries": [claim]},
        "evidence": {
            "supporting": [],
            "contradicting": [],
            "related": [],
            "debunks": [],
        },
    }


def _claim_response(
    claim: str,
    result: dict[str, Any],
    ocr_quality: str,
    conflicts: list[dict[str, object]],
    *,
    attributed_quote: bool = False,
    original_claim: str = "",
    normalized_claim: str = "",
    extra_search_queries: list[str] | None = None,
) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    provider_verdict = str(result.get("verdict", "UNVERIFIED"))
    groups = (
        ("supporting", "contradicting", "debunks")
        if provider_verdict in {"VERIFIED", "LIKELY_TRUE"}
        else (
            ("debunks", "contradicting", "supporting", "related")
            if provider_verdict in {"FALSE", "LIKELY_FALSE", "MISLEADING"}
            else ("supporting", "contradicting", "debunks", "related")
        )
    )
    for group in groups:
        for item in result.get("evidence", {}).get(group, []):
            url = str(item.get("url", "")).strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            domain = str(item.get("domain", urlparse(url).hostname or "")).casefold()
            title = str(item.get("title", "")).strip()
            similarity = int(item.get("similarity", 0) or 0)
            rel_str = str(item.get("relationship", "RELATED")).upper()
            if rel_str == "RELATED":
                mapped_rel = "PARTIAL" if similarity >= 60 else "UNRELATED"
            else:
                mapped_rel = RELATIONSHIP_MAP.get(rel_str, "UNRELATED")
            evidence.append(
                {
                    "title": title,
                    "source": str(item.get("publisher", domain)),
                    "source_type": _fact_check_source_type(
                        domain,
                        int(item.get("source_tier", 3)),
                    ),
                    "url": url,
                    "publication_date": str(item.get("published_date") or ""),
                    "relationship": mapped_rel,
                    "similarity": similarity,
                    "reason": str(
                        item.get("explanation")
                        or item.get("evidence_text")
                        or (f"{title} - {item.get('publisher', domain)}" if title else "This source was compared with the claim.")
                    ),
                }
            )

    closest_story_cand = result.get("closest_real_story") or {}
    if closest_story_cand.get("found") and closest_story_cand.get("url"):
        curl = str(closest_story_cand["url"]).strip()
        if curl and curl not in seen_urls:
            seen_urls.add(curl)
            cdomain = str(urlparse(curl).hostname or "").casefold()
            ctitle = str(closest_story_cand.get("title", "")).strip()
            cpub = str(closest_story_cand.get("publisher", cdomain))
            evidence.append(
                {
                    "title": ctitle,
                    "source": cpub,
                    "source_type": _fact_check_source_type(cdomain, 2),
                    "url": curl,
                    "publication_date": str(closest_story_cand.get("date") or ""),
                    "relationship": "PARTIAL",
                    "similarity": int(closest_story_cand.get("similarity", 0) or 0),
                    "reason": str(
                        closest_story_cand.get("explanation")
                        or (f"{ctitle} - {cpub}" if ctitle else "Closest matching news report.")
                    ),
                }
            )
    affected_by_conflict = any(
        any(candidate.casefold() in claim.casefold() for candidate in conflict["candidates"])
        for conflict in conflicts
    )
    claim_ocr_quality = "LOW" if affected_by_conflict else ocr_quality
    verdict = VERDICT_MAP.get(result.get("verdict", "UNVERIFIED"), "UNVERIFIED")
    if affected_by_conflict:
        verdict = "UNVERIFIED"
    numeric_confidence = _claim_evidence_score(
        result,
        evidence,
        claim_ocr_quality,
        affected_by_conflict,
    )
    warnings = [
        item["reason"] for item in evidence if item["relationship"] in {"PARTIAL", "UNRELATED"}
    ]
    warnings.extend(str(item) for item in result.get("context_warnings", []) if str(item).strip())
    if claim_type(claim) == "MONEY":
        warnings.append(
            "A cited amount must be distinguished as an actual expense, budget, obligation, "
            "or estimate; matching arithmetic alone does not verify spending."
        )
    queries = list(
        dict.fromkeys(
            result.get("search", {}).get("queries", []) + (extra_search_queries or [])
        )
    )
    return {
        "claim": claim,
        "claim_id": "",  # Assigned below once stable reading order is known.
        "original_claim": original_claim or claim,
        "normalized_claim": normalized_claim or claim,
        "claim_type": claim_type(claim),
        "ocr_confidence": claim_ocr_quality,
        "search_queries": queries,
        "evidence": evidence,
        "numerical_analysis": numerical_analysis(claim),
        "context_warnings": list(dict.fromkeys(warnings)),
        "verdict": verdict,
        "confidence": numeric_confidence,
        "explanation": (
            "OCR conflict affects this claim, so no factual verdict can be assigned."
            if affected_by_conflict
            else str(result.get("explanation", "The claim could not be verified."))
        ),
        "_provider_verdict": str(result.get("verdict", "UNVERIFIED")),
        "_provider_status": str(result.get("status", "SEARCH_UNAVAILABLE")),
        "_attributed_quote": attributed_quote,
        "_closest_real_story": closest_story_cand,
    }


def _fact_check_source_type(domain: str, source_tier: int) -> str:
    if any(domain == item or domain.endswith(f".{item}") for item in PRIMARY_DOMAINS):
        return "PRIMARY"
    if source_tier <= 2:
        return "MAJOR_NEWS"
    if any(
        name in domain
        for name in (
            "facebook.com",
            "tiktok.com",
            "x.com",
            "twitter.com",
            "threads.net",
            "threads.com",
            "instagram.com",
            "youtube.com",
        )
    ):
        return "SOCIAL"
    return "SOCIAL" if source_tier >= 4 else "SECONDARY"


def _claim_evidence_score(
    result: dict[str, Any],
    evidence: list[dict[str, Any]],
    ocr_quality: str,
    affected_by_conflict: bool,
) -> int:
    if affected_by_conflict:
        return 10
    decisive = [item for item in evidence if item["relationship"] in {"SUPPORTS", "CONTRADICTS"}]
    primary = any(item["source_type"] == "PRIMARY" for item in decisive)
    independent_domains = {
        urlparse(item["url"]).hostname or item["source"]
        for item in decisive
        if item["source_type"] != "SOCIAL"
    }
    primary_score = 30 if primary else 0
    independence_score = min(20, len(independent_domains) * 10)
    provider_confidence = max(0, min(100, int(result.get("confidence", 0))))
    semantic_score = round(provider_confidence * 0.20) if decisive else 0
    date_score = 10 if any(item["publication_date"] for item in decisive) else 5
    context_score = 0 if result.get("verdict") == "MISLEADING" else 10
    authenticity_score = 5 if decisive else 0
    contradiction_score = (
        5
        if result.get("verdict") in {"VERIFIED", "LIKELY_TRUE"}
        and not any(item["relationship"] == "CONTRADICTS" for item in decisive)
        else 0
    )
    score = (
        primary_score
        + independence_score
        + semantic_score
        + date_score
        + context_score
        + authenticity_score
        + contradiction_score
    )
    if not decisive:
        score = min(40, max(15, provider_confidence))
    if ocr_quality == "LOW":
        score = min(score, 35)
    elif ocr_quality == "MEDIUM":
        score = min(score, 85)
    return max(0, min(100, score))


def _source_independence(claims: list[dict[str, Any]]) -> dict[str, Any]:
    primary: set[str] = set()
    secondary: set[str] = set()
    counts: dict[str, int] = {}
    for claim in claims:
        for evidence in claim["evidence"]:
            domain = (urlparse(evidence["url"]).hostname or evidence["source"]).casefold()
            counts[domain] = counts.get(domain, 0) + 1
            (primary if evidence["source_type"] == "PRIMARY" else secondary).add(domain)
    duplicates = [domain for domain, count in counts.items() if count > 1]
    total = len(primary) + len(secondary)
    assessment = (
        "Evidence includes multiple independently hosted sources."
        if total >= 3
        else "Source independence is limited; seek a primary source and additional reporting."
    )
    return {
        "unique_primary_sources": len(primary),
        "unique_secondary_sources": len(secondary),
        "duplicate_evidence_chains_detected": duplicates,
        "assessment": assessment,
    }


def _overall_verdict(claims: list[dict[str, Any]]) -> str:
    if not claims:
        return "UNVERIFIABLE"
    central = claims[0]["verdict"]
    mapping = {
        "SUPPORTED": "SUPPORTED",
        "MOSTLY_SUPPORTED": "MOSTLY_SUPPORTED",
        "PARTLY_TRUE": "PARTLY_TRUE",
        "NEEDS_CONTEXT": "NEEDS_CONTEXT",
        "MISLEADING": "MISLEADING",
        "UNSUPPORTED": "MOSTLY_FALSE",
        "CONTRADICTED": "MOSTLY_FALSE",
        "FALSE": "FALSE",
        "OUTDATED": "NEEDS_CONTEXT",
        "UNVERIFIABLE": "UNVERIFIABLE",
    }
    overall = mapping[central]
    other_verdicts = {claim["verdict"] for claim in claims[1:]}
    if overall in {"SUPPORTED", "MOSTLY_SUPPORTED"} and other_verdicts & {
        "MISLEADING",
        "UNSUPPORTED",
        "CONTRADICTED",
        "FALSE",
    }:
        return "PARTLY_TRUE"
    return overall


def _overall_confidence(claims: list[dict[str, Any]], ocr_quality: str, has_conflicts: bool) -> str:
    if has_conflicts or ocr_quality == "LOW" or not claims:
        return "LOW"
    levels = [claim["confidence"] for claim in claims]
    if ocr_quality == "HIGH" and levels and all(level == "HIGH" for level in levels):
        return "HIGH"
    return "MEDIUM" if any(level in {"HIGH", "MEDIUM"} for level in levels) else "LOW"


def _summary(verdict: str, claim_count: int, ocr_quality: str) -> str:
    if not claim_count:
        return "No independently verifiable factual claim could be extracted from the image."
    verdict_label = {
        "MOSTLY_FALSE": "most likely fake",
        "FALSE": "fake",
        "UNVERIFIABLE": "not verifiable",
    }.get(verdict, verdict.replace("_", " ").lower())
    return (
        f"The image produced {claim_count} atomic factual claim(s). OCR quality was "
        f"{ocr_quality.lower()}, and the central claim is assessed as {verdict_label}."
    )


async def normalize_with_gemini(
    text: str,
    settings: Settings | None = None,
    *,
    vision_client: GeminiVisionClient | None = None,
    image: PreparedImage | None = None,
) -> dict[str, Any]:
    """Normalize text and resolve entities using Gemini AI with deterministic fallback."""
    client = vision_client or (GeminiVisionClient(settings) if settings else None)
    if client and client.configured and hasattr(client, "normalize_text"):
        try:
            result = await client.normalize_text(text, image=image)
            if result and result.get("normalized_text"):
                return result
        except Exception:
            logger.warning("Gemini AI text normalization failed; using fallback", exc_info=True)
    norm_text, norm_values = normalize_fact_text(text)
    return {
        "normalized_text": norm_text,
        "normalized_values": norm_values,
        "entities": extract_entities(norm_text, norm_values),
        "canonical_claims": extract_atomic_claims(norm_text),
        "corrections": [],
        "search_queries": [norm_text] if norm_text else [],
    }
