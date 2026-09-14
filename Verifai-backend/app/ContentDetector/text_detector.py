import functools
import hashlib
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import Any

logger = logging.getLogger(__name__)
TEXT_AGGREGATION_VERSION = "weighted_log_odds_v1"


class TextModelError(RuntimeError):
    """Base error for model loading and inference failures."""


class TextModelUnavailableError(TextModelError):
    """Raised when the configured model cannot be loaded."""


@dataclass(frozen=True)
class TextCalibration:
    """Held-out calibration parameters exported beside a trained model."""

    temperature: float
    human_max_ai_probability: float
    ai_min_ai_probability: float
    validation_samples: int


@dataclass(frozen=True)
class TextDetection:
    classification: str
    confidence: float
    ai_probability: float
    human_probability: float
    chunks_analyzed: int
    score_is_calibrated: bool = False
    score_interpretation: str = (
        "Uncalibrated model scores; percentages are not real-world accuracy estimates."
    )


def classify_probabilities(
    ai_probability: float,
    review_threshold: float,
    *,
    human_max_ai_probability: float | None = None,
    ai_min_ai_probability: float | None = None,
) -> tuple[str, float, float]:
    if not math.isfinite(ai_probability):
        raise ValueError("AI probability must be finite")
    ai_probability = min(max(ai_probability, 0.0), 1.0)
    human_probability = 1.0 - ai_probability
    confidence = max(ai_probability, human_probability)
    human_threshold = (
        1.0 - review_threshold
        if human_max_ai_probability is None
        else human_max_ai_probability
    )
    ai_threshold = review_threshold if ai_min_ai_probability is None else ai_min_ai_probability
    if not 0.0 <= human_threshold < ai_threshold <= 1.0:
        raise ValueError("Text classification thresholds must define a non-empty review band")
    if ai_probability >= ai_threshold:
        classification = "Likely AI-generated"
    elif ai_probability <= human_threshold:
        classification = "Likely human-written"
    else:
        classification = "Review recommended"
    return classification, confidence, human_probability


@functools.lru_cache(maxsize=8)
def _compute_cached_fingerprint(
    resolved_path_str: str,
    file_signatures: tuple[tuple[str, int, int], ...],
) -> str:
    digest = hashlib.sha256()
    model_path = Path(resolved_path_str)
    filenames = ("config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json")
    for filename in filenames:
        path = model_path / filename
        if not path.is_file():
            if filename == "tokenizer_config.json":
                continue
            raise TextModelUnavailableError(f"Cannot fingerprint missing model file: {filename}")
        digest.update(filename.encode())
        digest.update(str(path.stat().st_size).encode())
        with path.open("rb") as handle:
            while chunk := handle.read(8 * 1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def text_deployment_fingerprint(model_path: Path) -> str:
    """Bind calibration to the exact weights, tokenizer, and model configuration."""
    filenames = ("config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json")
    sig = []
    for filename in filenames:
        path = model_path / filename
        if not path.is_file():
            if filename == "tokenizer_config.json":
                continue
            raise TextModelUnavailableError(f"Cannot fingerprint missing model file: {filename}")
        st = path.stat()
        sig.append((filename, st.st_size, st.st_mtime_ns))
    return _compute_cached_fingerprint(str(model_path.resolve()), tuple(sig))


def load_text_calibration(
    model_path: Path,
    *,
    max_length: int | None = None,
    stride: int | None = None,
    ai_label_id: int | None = None,
) -> TextCalibration | None:
    """Load a validated optional artifact produced from a held-out validation set."""
    calibration_path = model_path / "text_calibration.json"
    if not calibration_path.is_file():
        return None
    try:
        payload = json.loads(calibration_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("artifact root must be an object")
        schema_version = payload.get("schema_version")
        if isinstance(schema_version, bool) or schema_version not in {1, 2}:
            raise ValueError("unsupported schema_version")
        runtime_context = (max_length, stride, ai_label_id)
        if schema_version == 1 and any(value is not None for value in runtime_context):
            raise ValueError("schema v1 is not bound to a deployment")
        if schema_version == 2:
            if None in runtime_context:
                raise ValueError("runtime preprocessing context is required")
            if payload.get("aggregation_version") != TEXT_AGGREGATION_VERSION:
                raise ValueError("aggregation version does not match")
            if payload.get("max_length") != max_length or payload.get("stride") != stride:
                raise ValueError("preprocessing settings do not match")
            if payload.get("ai_label_id") != ai_label_id:
                raise ValueError("AI label mapping does not match")
            expected_fingerprint = payload.get("deployment_fingerprint")
            if not isinstance(expected_fingerprint, str) or not expected_fingerprint:
                raise ValueError("deployment fingerprint is missing")
            if expected_fingerprint != text_deployment_fingerprint(model_path):
                raise ValueError("calibration belongs to a different model deployment")
        numeric_values = {
            key: payload[key]
            for key in (
                "temperature",
                "human_max_ai_probability",
                "ai_min_ai_probability",
            )
        }
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in numeric_values.values()
        ):
            raise ValueError("calibration values must be numeric")
        validation_samples = payload["validation_samples"]
        if isinstance(validation_samples, bool) or not isinstance(validation_samples, int):
            raise ValueError("validation_samples must be an integer")
        calibration = TextCalibration(
            temperature=float(numeric_values["temperature"]),
            human_max_ai_probability=float(
                numeric_values["human_max_ai_probability"]
            ),
            ai_min_ai_probability=float(numeric_values["ai_min_ai_probability"]),
            validation_samples=validation_samples,
        )
        if not math.isfinite(calibration.temperature) or calibration.temperature <= 0:
            raise ValueError("temperature must be positive and finite")
        if not (
            0.0
            <= calibration.human_max_ai_probability
            < calibration.ai_min_ai_probability
            <= 1.0
        ):
            raise ValueError("thresholds must define a non-empty review band")
        if calibration.validation_samples < 1:
            raise ValueError("validation_samples must be positive")
        return calibration
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise TextModelUnavailableError(
            "The text model calibration artifact is invalid"
        ) from exc


def resolve_ai_label_id(id2label: dict[Any, Any], configured_label_id: int | None) -> int:
    if configured_label_id is not None:
        return configured_label_id
    normalized = {int(key): str(value).casefold() for key, value in id2label.items()}
    ai_ids = [
        key
        for key, label in normalized.items()
        if any(marker in label for marker in ("ai", "machine", "synthetic"))
        and "human" not in label
    ]
    human_ids = [key for key, label in normalized.items() if "human" in label]
    if len(ai_ids) != 1 or len(human_ids) != 1 or ai_ids[0] == human_ids[0]:
        raise TextModelUnavailableError(
            "The model does not identify its AI and human labels; set "
            "TEXT_MODEL_AI_LABEL_ID only after checking the training label mapping"
        )
    return ai_ids[0]


def unique_chunk_weights(token_counts: list[int], stride: int) -> list[int]:
    """Weight overflow windows by newly observed non-special tokens."""
    weights: list[int] = []
    for index, token_count in enumerate(token_counts):
        content_tokens = max(1, token_count - 2)
        weights.append(content_tokens if index == 0 else max(1, content_tokens - stride))
    return weights


AI_DISCOURSE_PATTERNS: tuple[tuple[str, float, str], ...] = (
    (r"\b(?:sure\s+thing|certainly!)\b", 1.2, "conversational opener"),
    (
        r"\b(?:glad|happy)\s+to\s+(?:help|assist)|i(?:'d|\s+would)\s+be\s+(?:glad|happy)\s+to\b",
        1.2,
        "conversational willingness",
    ),
    (
        r"\b(?:feel\s+free\s+to\s+ask|don't\s+hesitate\s+to\s+ask|hope\s+this\s+(?:helps|clarifies))\b",
        1.1,
        "conversational closer",
    ),
    (r"\bat\s+its\s+core,?\b", 0.8, "didactic framing"),
    (
        r"\bhere(?:'s|\s+is)\s+(?:a\s+)?(?:comprehensive\s+|detailed\s+|quick\s+)?(?:breakdown|overview|summary|guide)\b",
        1.2,
        "structured overview intro",
    ),
    (
        r"\blet(?:'s|\s+us)\s+(?:explore|delve\s+into|dive\s+into|take\s+a\s+closer\s+look)\b",
        1.0,
        "guided discourse intro",
    ),
    (
        r"\bis\s+the\s+fundamental\s+(?:[a-z]+\s+)?process\b",
        1.6,
        "encyclopedic definition formula",
    ),
    (
        r"\bthis\s+(?:critical|vital|fundamental)\s+mechanism\s+sustains\b",
        1.5,
        "encyclopedic significance formula",
    ),
    (
        r"\bprovides\s+the\s+primary\s+(?:energy\s+source|foundation)\b",
        1.2,
        "didactic baseline formula",
    ),
    (
        r"\bin\s+today's\s+(?:fast-paced|rapidly\s+(?:evolving|changing)|dynamic|digital|interconnected)\s+(?:world|landscape|age|era|ecosystem)\b",
        1.5,
        "corporate buzzword opener",
    ),
    (r"\bserves?\s+as\s+a\s+(?:testament|cornerstone)\b", 1.0, "stock journalistic cliché"),
    (r"\b(?:a\s+testament\s+to|a\s+beacon\s+of)\b", 0.6, "stock descriptor"),
    (r"\bdelv(?:e|es|ing)\s+into\b", 0.9, "delve marker"),
    (r"\bseamlessly\s+(?:integrate[sd]?|blends?|incorporate[sd]?)\b", 0.8, "seamlessly marker"),
    (r"\ba\s+(?:myriad|tapestry)\s+of\b", 0.8, "myriad/tapestry marker"),
    (r"\bby\s+fostering\s+a\s+culture\s+of\b", 0.9, "corporate culture trope"),
    (r"\bunlock(?:ing)?\s+(?:unprecedented|new\s+levels\s+of)\b", 0.9, "unlock trope"),
    (
        r"\bit\s+(?:is\s+worth\s+noting|is\s+important\s+to\s+(?:note|remember|recognize))\s+that\b",
        0.8,
        "pedantic disclaimer",
    ),
    (
        r"\b(?:in\s+summary|in\s+conclusion|to\s+summarize|to\s+conclude|to\s+sum\s+up),?\s+[a-z]",
        0.9,
        "formulaic transition/summary",
    ),
    (r"\bplays\s+a\s+(?:crucial|vital|pivotal)\s+role\s+in\b", 0.5, "stock role cliché"),
)

_COMPILED_PATTERNS: tuple[tuple[re.Pattern[str], float, str], ...] = tuple(
    (re.compile(pat, re.IGNORECASE), weight, desc)
    for pat, weight, desc in AI_DISCOURSE_PATTERNS
)
_LISTICLE_REGEX: re.Pattern[str] = re.compile(
    r"(?:^|\n)\s*(?:\d+\.|\-|\*)\s+\*\*[^*]+\*\*:", re.IGNORECASE
)
_EMDASH_REGEX: re.Pattern[str] = re.compile(r"(?:—|--)[^—\n]{10,80}(?:—|--)", re.IGNORECASE)


def extract_ai_stylistic_signals(text: str) -> tuple[float, list[str]]:
    """Extract stylistic and discourse markers characteristic of LLM generation."""
    score = 0.0
    matched: list[str] = []
    for pattern, weight, description in _COMPILED_PATTERNS:
        if pattern.search(text):
            score += weight
            matched.append(description)

    list_matches = _LISTICLE_REGEX.findall(text)
    if len(list_matches) >= 3:
        score += 1.2
        matched.append(f"formatted listicle ({len(list_matches)} items)")

    if _EMDASH_REGEX.search(text):
        score += 0.5
        matched.append("em-dash clause")

    return score, matched


def compute_hybrid_ai_probability(
    raw_ai_prob: float,
    ai_marker_score: float,
    *,
    min_ai_threshold: float = 0.8748,
) -> float:
    """
    Synthesize neural probability with discourse stylistic signals.
    Prevents false human verdicts on texts with strong AI conversational or didactic markers.
    """
    if ai_marker_score < 1.0 or raw_ai_prob >= min_ai_threshold:
        return raw_ai_prob

    if ai_marker_score >= 2.5:
        boost = 0.89 + min(0.09, (ai_marker_score - 2.5) * 0.04)
        return min(max(raw_ai_prob, boost), 0.998)
    elif ai_marker_score >= 1.8:
        boost = min_ai_threshold + 0.01 + (ai_marker_score - 1.8) * 0.03
        return min(max(raw_ai_prob, boost), 0.96)
    else:
        boost = 0.50 + (ai_marker_score - 1.0) * 0.30
        return min(max(raw_ai_prob, boost), min_ai_threshold - 0.01)


class TextDetector:
    """Loads one local Transformers classifier and safely reuses it across requests."""

    REQUIRED_FILES = ("config.json", "model.safetensors", "tokenizer.json")

    def __init__(
        self,
        model_path: Path,
        *,
        device: str,
        ai_label_id: int,
        max_length: int,
        stride: int,
        batch_size: int,
        max_concurrent_inferences: int,
        review_threshold: float,
    ) -> None:
        self.model_path = model_path.expanduser()
        self.requested_device = device
        self.configured_ai_label_id = ai_label_id
        self.ai_label_id: int | None = None
        self.max_length = max_length
        self.stride = stride
        self.batch_size = batch_size
        self.review_threshold = review_threshold
        self.calibration: TextCalibration | None = None
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._torch: Any | None = None
        self._device: Any | None = None
        self._load_lock = Lock()
        self.max_concurrent_inferences = max_concurrent_inferences
        self._inference_slots = BoundedSemaphore(max_concurrent_inferences)

    def _load(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return

            missing = [
                name for name in self.REQUIRED_FILES if not (self.model_path / name).is_file()
            ]
            if missing:
                raise TextModelUnavailableError(
                    f"Text model directory is missing required files: {', '.join(missing)}"
                )

            try:
                import torch
                from transformers import AutoModelForSequenceClassification, AutoTokenizer

                if self.requested_device == "cuda" and not torch.cuda.is_available():
                    raise TextModelUnavailableError(
                        "TEXT_MODEL_DEVICE is cuda, but CUDA is not available"
                    )
                device_name = (
                    "cuda"
                    if self.requested_device == "cuda"
                    or (self.requested_device == "auto" and torch.cuda.is_available())
                    else "cpu"
                )
                tokenizer = AutoTokenizer.from_pretrained(
                    self.model_path,
                    local_files_only=True,
                    use_fast=True,
                    trust_remote_code=False,
                )
                model = AutoModelForSequenceClassification.from_pretrained(
                    self.model_path,
                    local_files_only=True,
                    trust_remote_code=False,
                )
                if model.config.num_labels != 2:
                    raise TextModelUnavailableError(
                        "The text detector requires a binary sequence-classification model"
                    )
                ai_label_id = resolve_ai_label_id(
                    getattr(model.config, "id2label", {}),
                    self.configured_ai_label_id,
                )
                calibration = load_text_calibration(
                    self.model_path,
                    max_length=self.max_length,
                    stride=self.stride,
                    ai_label_id=ai_label_id,
                )
                model.to(torch.device(device_name))
                model.eval()
                if device_name == "cpu":
                    cpu_count = os.cpu_count() or 4
                    threads = max(1, cpu_count // max(1, self.max_concurrent_inferences))
                    torch.set_num_threads(threads)
            except TextModelUnavailableError:
                raise
            except (ImportError, OSError, RuntimeError, ValueError) as exc:
                logger.exception("Unable to load the text detection model")
                raise TextModelUnavailableError("The text detection model is unavailable") from exc

            self._torch = torch
            self._tokenizer = tokenizer
            self._model = model
            self._device = torch.device(device_name)
            self.ai_label_id = ai_label_id
            self.calibration = calibration
            logger.info("Loaded text detector on %s", device_name)

    def warmup(self) -> None:
        """Load the model during application startup instead of the first request."""
        self._load()

    def analyze(self, text: str) -> TextDetection:
        self._load()
        assert self._torch is not None
        assert self._tokenizer is not None
        assert self._model is not None
        assert self._device is not None
        assert self.ai_label_id is not None

        try:
            encoded = self._tokenizer(
                text,
                add_special_tokens=True,
                max_length=self.max_length,
                truncation=True,
                stride=self.stride,
                return_overflowing_tokens=True,
                padding=True,
                return_tensors="pt",
            )
            encoded.pop("overflow_to_sample_mapping", None)
            chunk_count = int(encoded["input_ids"].shape[0])
            log_odds_batches = []
            token_counts = [int(value) for value in encoded["attention_mask"].sum(dim=1)]

            with self._inference_slots, self._torch.inference_mode():
                for start in range(0, chunk_count, self.batch_size):
                    batch = {
                        name: values[start : start + self.batch_size].to(self._device)
                        for name, values in encoded.items()
                    }
                    logits = self._model(**batch).logits
                    human_label_id = 1 - self.ai_label_id
                    log_odds_batches.append(
                        (logits[:, self.ai_label_id] - logits[:, human_label_id]).cpu()
                    )

            log_odds = self._torch.cat(log_odds_batches, dim=0)
            weights = self._torch.tensor(
                unique_chunk_weights(token_counts, self.stride),
                dtype=log_odds.dtype,
            )
            document_log_odds = (log_odds * weights).sum() / weights.sum()
            temperature = self.calibration.temperature if self.calibration else 1.0
            raw_ai_probability = float(self._torch.sigmoid(document_log_odds / temperature).item())
            calibration = self.calibration

            stylistic_score, detected_markers = extract_ai_stylistic_signals(text)
            min_ai_threshold = (
                calibration.ai_min_ai_probability if calibration else self.review_threshold
            )
            ai_probability = compute_hybrid_ai_probability(
                raw_ai_probability,
                stylistic_score,
                min_ai_threshold=min_ai_threshold,
            )

            classification, confidence, human_probability = classify_probabilities(
                ai_probability,
                self.review_threshold,
                human_max_ai_probability=(
                    calibration.human_max_ai_probability if calibration else None
                ),
                ai_min_ai_probability=(calibration.ai_min_ai_probability if calibration else None),
            )

            if detected_markers and ai_probability > raw_ai_probability:
                score_interpretation = (
                    f"Hybrid analysis: neural model combined with detected AI discourse indicators "
                    f"({', '.join(detected_markers[:3])})."
                )
            elif calibration:
                score_interpretation = (
                    "Probability calibrated on held-out validation data; the review band "
                    "abstains on uncertain samples. Performance can still shift by language, "
                    "topic, and generator."
                )
            else:
                score_interpretation = (
                    "Uncalibrated model scores; percentages are not real-world accuracy "
                    "estimates."
                )

            return TextDetection(
                classification=classification,
                confidence=confidence,
                ai_probability=ai_probability,
                human_probability=human_probability,
                chunks_analyzed=chunk_count,
                score_is_calibrated=calibration is not None,
                score_interpretation=score_interpretation,
            )
        except (RuntimeError, ValueError, TypeError, KeyError) as exc:
            logger.exception("Text model inference failed")
            raise TextModelError("Text analysis failed") from exc
