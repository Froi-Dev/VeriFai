import logging
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


class TextModelError(RuntimeError):
    """Base error for model loading and inference failures."""


class TextModelUnavailableError(TextModelError):
    """Raised when the configured model cannot be loaded."""


@dataclass(frozen=True)
class TextDetection:
    classification: str
    confidence: float
    ai_probability: float
    human_probability: float
    chunks_analyzed: int


def classify_probabilities(
    ai_probability: float, review_threshold: float
) -> tuple[str, float, float]:
    ai_probability = min(max(ai_probability, 0.0), 1.0)
    human_probability = 1.0 - ai_probability
    confidence = max(ai_probability, human_probability)
    if ai_probability >= review_threshold:
        classification = "Likely AI-generated"
    elif human_probability >= review_threshold:
        classification = "Likely human-written"
    else:
        classification = "Review recommended"
    return classification, confidence, human_probability


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
        review_threshold: float,
    ) -> None:
        self.model_path = model_path.expanduser()
        self.requested_device = device
        self.ai_label_id = ai_label_id
        self.max_length = max_length
        self.stride = stride
        self.batch_size = batch_size
        self.review_threshold = review_threshold
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._torch: Any | None = None
        self._device: Any | None = None
        self._load_lock = Lock()
        self._inference_lock = Lock()

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
                model.to(torch.device(device_name))
                model.eval()
            except TextModelUnavailableError:
                raise
            except (ImportError, OSError, RuntimeError, ValueError) as exc:
                logger.exception("Unable to load the text detection model")
                raise TextModelUnavailableError("The text detection model is unavailable") from exc

            self._torch = torch
            self._tokenizer = tokenizer
            self._model = model
            self._device = torch.device(device_name)
            logger.info("Loaded text detector on %s", device_name)

    def analyze(self, text: str) -> TextDetection:
        self._load()
        assert self._torch is not None
        assert self._tokenizer is not None
        assert self._model is not None
        assert self._device is not None

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
            probability_batches = []

            with self._inference_lock, self._torch.inference_mode():
                for start in range(0, chunk_count, self.batch_size):
                    batch = {
                        name: values[start : start + self.batch_size].to(self._device)
                        for name, values in encoded.items()
                    }
                    logits = self._model(**batch).logits
                    probability_batches.append(self._torch.softmax(logits, dim=-1).cpu())

            mean_probabilities = self._torch.cat(probability_batches, dim=0).mean(dim=0)
            ai_probability = float(mean_probabilities[self.ai_label_id].item())
            classification, confidence, human_probability = classify_probabilities(
                ai_probability, self.review_threshold
            )
            return TextDetection(
                classification=classification,
                confidence=confidence,
                ai_probability=ai_probability,
                human_probability=human_probability,
                chunks_analyzed=chunk_count,
            )
        except (RuntimeError, ValueError, TypeError, KeyError) as exc:
            logger.exception("Text model inference failed")
            raise TextModelError("Text analysis failed") from exc
