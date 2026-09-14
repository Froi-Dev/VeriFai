"""Structured verification audit logging for VeriFai.

Provides detailed end-to-end tracing of the fact-checking decision process:
- Claim breakdown & atomic sub-claims
- Multi-round queries and provider outcomes
- Selected vs. rejected sources with justification
- Evidence passages and detected contradictions
- Adjudication rationale and stopping criteria
"""

import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("verifai.audit")


@dataclass
class VerificationAuditRecord:
    verification_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    claim_raw: str = ""
    claim_cleaned: str = ""
    claim_type: str = "FACT"
    atomic_claims: list[str] = field(default_factory=list)
    negation_detected: bool = False
    modality: str = "ASSERTED"
    search_rounds: int = 1
    queries_issued: list[str] = field(default_factory=list)
    providers_used: list[str] = field(default_factory=list)
    total_results_found: int = 0
    selected_sources: list[dict[str, Any]] = field(default_factory=list)
    rejected_sources: list[dict[str, Any]] = field(default_factory=list)
    evidence_passages: list[dict[str, str]] = field(default_factory=list)
    contradictions_count: int = 0
    unresolved_numeric_claims: list[str] = field(default_factory=list)
    verdict: str = "UNVERIFIED"
    confidence: int = 0
    adjudication_source: str = "rules"
    stopping_reason: str = "completed"
    duration_ms: float = 0.0
    # --- Image pipeline instrumentation (optional, set by ImageScanner) ---
    input_type: str = "text"
    ocr_provider: str | None = None
    ocr_duration_ms: float | None = None
    ocr_success: bool | None = None
    ocr_fallback_used: bool | None = None
    cleaned_text_length: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False)


class AuditLogger:
    """Manages appending audit records to a structured JSONL sink and logging."""

    def __init__(self, log_path: str | Path | None = None, enabled: bool = True) -> None:
        self.enabled = enabled
        self.log_path = Path(log_path) if log_path else None
        if self.enabled and self.log_path:
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                logger.warning("Could not create directory for audit log: %s", exc)

    def record(self, record: VerificationAuditRecord) -> None:
        if not self.enabled:
            return

        try:
            line = record.to_json()
            # Log structured summary
            logger.info(
                "VERIFICATION_AUDIT [%s] verdict=%s conf=%d source=%s stop=%s",
                record.verification_id,
                record.verdict,
                record.confidence,
                record.adjudication_source,
                record.stopping_reason,
            )
            # Write to JSONL file if path is specified
            if self.log_path:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception as exc:
            logger.warning("Failed to write verification audit record: %s", exc)
