"""Gemini-backed text AI-content detector.

Drop-in replacement for the RoBERTa ``TextDetector`` that delegates
classification to the Gemini Generative Language API while returning the
exact same ``TextDetection`` dataclass so that routes, schemas, and the
React frontend remain unchanged.

This module is a **temporary** stand-in used for usability testing while
the team lacks server resources to host the 1.2 GB fine-tuned RoBERTa
model.  Restore the model-based analyzer by setting
``TEXT_ANALYZER_BACKEND=roberta`` in ``.env``.
"""

import asyncio
import json
import logging
import math
import threading

from app.ContentDetector.text_detector import (
    TextDetection,
    TextModelError,
    TextModelUnavailableError,
    classify_probabilities,
    compute_hybrid_ai_probability,
    extract_ai_stylistic_signals,
    extract_human_informal_signals,
)
from app.FakeNewsAnalyzer.image_fact_checker import GeminiVisionClient, OcrUnavailableError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini prompt and structured output schema
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are an expert AI-text forensic classifier specialized in detecting text "
    "generated or rewritten by modern LLMs (such as GPT-4o, Claude 3.5 Sonnet, "
    "DeepSeek-R1, Gemini 2.0/1.5, LLaMA, and ChatGPT).\n\n"
    "CRITICAL CONTEXT:\n"
    "Modern AI does NOT merely produce formal academic essays with 'delve' or "
    "'in conclusion'. Modern AI models regularly generate:\n"
    "- Casual social media comments, short observations, and lifestyle banter.\n"
    "- Conversational Tagalog, Filipino, and Taglish text.\n"
    "- Practical recipes, tutorials, short advice, and summaries.\n"
    "- Reflective personal essays and simulated first-person opinions.\n\n"
    "EVALUATION CRITERIA:\n"
    "1. BURSTINESS & CADENCE:\n"
    "   - AI text has low burstiness: uniform sentence lengths (typically 12-25 words), "
    "balanced subordinate clauses, and smooth metered rhythm throughout.\n"
    "   - Human writing has high variance: fragmented thoughts, ultra-short punchy lines, "
    "spontaneous run-ons, irregular punctuation, and sudden shifts.\n"
    "2. PERPLEXITY & PREDICTABILITY:\n"
    "   - AI text selects high-probability collocations, polished transition pacing, "
    "standard syntax templates, and balanced arguments.\n"
    "   - Human writing features idiosyncratic word pairings, genuine typos, emotional "
    "exaggeration, informal slang, and unstandardized syntax.\n"
    "3. SPECIFICITY & GROUNDING:\n"
    "   - AI text offers tidy, complete, generalized explanations without raw personal "
    "messiness or granular real-world grounding.\n"
    "   - Human casual text is often unpolished, incomplete, colloquial, and grounded in "
    "spontaneous local trivia.\n"
    "4. TAGALOG / TAGLISH AI SIGNATURES:\n"
    "   - AI Taglish exhibits unnaturally balanced grammatical frames, predictable "
    "code-switching boundaries, and polite didactic phrasing.\n"
    "   - Human Taglish features unstandardized street/internet slang (e.g., lods, pota, "
    "tara g, umay, skl, tbh), emotional swearing, chaotic spelling, and conversational ellipsis.\n\n"
    "FEW-SHOT CONTRASTIVE BENCHMARKS:\n"
    "[AI Example - Short Casual]: 'Can\\'t believe the karaoke next door fixed itself before anyone noticed.' -> AI (0.88, smooth tidy narrative)\n"
    "[AI Example - Taglish]: 'Gumagaan ba ito once yung blood pressure reading na nagulat pati yung nurse mismong habang tumatakbo pa yung linggong sobra na rin ang nangyayari?' -> AI (0.90, artificial clause stacking)\n"
    "[AI Example - Instructional]: 'To make chocolate chip cookies, first preheat your oven to 375 degrees Fahrenheit. In a large bowl, cream together softened butter...' -> AI (0.92, textbook recipe template)\n"
    "[AI Example - Reflection]: 'A simple weather advisory turned into a useful little lesson. The detail I almost missed was a delayed announcement...' -> AI (0.92, formulaic introspective summary)\n"
    "[Human Example - Raw Tagalog]: 'Yung tipong ang lakas na ng epekto sayo ng isang tao, na marinig mo lang yung pangalan nya, halo halong emosyon na nararamdaman mo. kaba, saya, excitement... :) Lolwhuttttt!' -> Human (0.05, genuine emotional burst and slang)\n"
    "[Human Example - Casual Slang]: 'haha tangina naman kasi niyan eh, nung grade 6 ako lagi kaming nagtatalo ng tropa ko kung ano mas masarap, jollibee o mcdo. di ko na kaya tbh' -> Human (0.05, authentic conversational slang)\n\n"
    "DECISIVENESS RULE:\n"
    "If the text exhibits standard AI predictability, tidy sentence structure, formulaic pacing, "
    "or generic fluency, assign ai_probability >= 0.80.\n"
    "If the text has authentic human flaws, raw emotion, informal colloquialisms, or erratic syntax, "
    "assign ai_probability <= 0.20."
)

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "ai_probability": {
            "type": "NUMBER",
        },
        "indicators": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "reason": {
            "type": "STRING",
        },
    },
    "required": ["ai_probability", "reason"],
}


# ---------------------------------------------------------------------------
# GeminiTextDetector
# ---------------------------------------------------------------------------

_sync_loop: asyncio.AbstractEventLoop | None = None
_sync_thread: threading.Thread | None = None
_sync_lock = threading.Lock()


def _get_sync_loop() -> asyncio.AbstractEventLoop:
    global _sync_loop, _sync_thread
    with _sync_lock:
        if _sync_loop is None or _sync_loop.is_closed():
            _sync_loop = asyncio.new_event_loop()
            _sync_thread = threading.Thread(target=_sync_loop.run_forever, daemon=True)
            _sync_thread.start()
        return _sync_loop


class GeminiTextDetector:
    """Classifies text using the Gemini API with identical interface to TextDetector."""

    def __init__(
        self,
        gemini_client: GeminiVisionClient,
        *,
        model: str = "gemini-3.5-flash-lite",
        review_threshold: float = 0.65,
    ) -> None:
        self.client = gemini_client
        self.model = model
        self.review_threshold = review_threshold

    # -- public interface (mirrors TextDetector) ----------------------------

    def warmup(self) -> None:
        """No-op.  Gemini does not need a local model warmup."""

    async def analyze_async(self, text: str) -> TextDetection:
        """Asynchronous analysis for FastAPI routes running on the event loop."""
        return await self._analyze_async(text)

    def analyze(self, text: str) -> TextDetection:
        """Synchronous wrapper for offline scripts and test runners."""
        loop = _get_sync_loop()
        future = asyncio.run_coroutine_threadsafe(self._analyze_async(text), loop)
        return future.result()

    # -- internal -----------------------------------------------------------

    async def _analyze_async(self, text: str) -> TextDetection:
        """Call Gemini, parse the structured response, normalize output."""

        # 1. Run local stylistic signal extraction (same as RoBERTa path)
        stylistic_score, detected_markers = extract_ai_stylistic_signals(text)
        human_informal_score, human_markers = extract_human_informal_signals(text)

        # 2. Call Gemini
        prompt = f"{_SYSTEM_PROMPT}\n\n--- TEXT TO CLASSIFY ---\n{text}\n--- END ---"

        try:
            raw = await self.client.generate(
                None,  # no image
                prompt,
                generation_config={
                    "temperature": 0,
                    "maxOutputTokens": 512,
                    "thinkingConfig": {"thinkingLevel": "minimal"},
                    "responseMimeType": "application/json",
                    "responseSchema": _RESPONSE_SCHEMA,
                },
                model=self.model,
            )
        except OcrUnavailableError as exc:
            raise TextModelUnavailableError(
                "Gemini text analysis is temporarily unavailable"
            ) from exc
        except Exception as exc:
            logger.exception("Gemini text analysis call failed")
            raise TextModelError("Text analysis could not be completed") from exc

        # 3. Parse structured JSON response
        try:
            result = json.loads(raw)
            raw_ai_probability = float(result["ai_probability"])
            indicators = [
                str(item).strip()
                for item in result.get("indicators", [])
                if str(item).strip()
            ]
            reason = str(result.get("reason", "")).strip()
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Gemini returned malformed text analysis JSON: %s", raw[:500])
            raise TextModelError(
                "The text analysis provider returned an invalid result"
            ) from exc

        # 4. Validate and clamp raw probability
        if not math.isfinite(raw_ai_probability):
            raw_ai_probability = 0.5
        raw_ai_probability = min(max(raw_ai_probability, 0.0), 1.0)

        # 5. Apply hybrid fusion matching the trained RoBERTa model protocol:
        # Synthesizes neural probability with discourse stylistic signals
        # and human casual safeguards.
        min_ai_threshold = self.review_threshold
        human_max_threshold = 1.0 - self.review_threshold

        ai_probability = compute_hybrid_ai_probability(
            raw_ai_probability,
            stylistic_score,
            human_marker_score=human_informal_score,
            min_ai_threshold=min_ai_threshold,
            human_max_threshold=human_max_threshold,
        )

        # 6. Derive classification using calibrated threshold boundaries
        classification, confidence, human_probability = classify_probabilities(
            ai_probability,
            self.review_threshold,
            human_max_ai_probability=human_max_threshold,
            ai_min_ai_probability=min_ai_threshold,
        )

        # 7. Build score interpretation
        if detected_markers and ai_probability >= min_ai_threshold:
            score_interpretation = (
                "Contains common formulaic phrasing patterns frequently seen "
                "in AI-generated text."
            )
        elif classification == "Likely human-written":
            score_interpretation = (
                "Estimated pattern likelihood based on writing style."
            )
        else:
            score_interpretation = (
                "Analysis complete. Percentages show estimated pattern match "
                "likelihood."
            )

        # 8. Combine detected discourse signals, forensic indicators, and reason
        all_signals: list[str] = list(detected_markers)
        for ind in indicators:
            if ind not in all_signals:
                all_signals.append(ind)
        if reason and reason not in all_signals:
            all_signals.append(reason)

        return TextDetection(
            classification=classification,
            confidence=confidence,
            ai_probability=ai_probability,
            human_probability=human_probability,
            chunks_analyzed=1,
            score_is_calibrated=False,
            score_interpretation=score_interpretation,
            model_name=f"gemini:{self.model}",
            signals=tuple(all_signals),
        )
