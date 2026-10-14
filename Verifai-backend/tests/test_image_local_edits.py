"""Decision guardrails, independent of the vision model's detection accuracy."""

import json
from unittest.mock import AsyncMock

import pytest

from app.FakeNewsAnalyzer.image_fact_checker import GeminiImageDetector, PreparedImage
from app.Global.schemas import ImageDetectionResponse


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("classification", "local_assessment", "observations", "expected"),
    [
        ("No clear AI signals", "suspected", ["Boundary discontinuity at the mouth."],
         "Manipulation suspected"),
        ("Likely authentic/camera-captured", "suspected", ["Text crosses the paper edge."],
         "Manipulation suspected"),
        ("No clear AI signals", "inconclusive", ["Letters are too small to resolve."],
         "Inconclusive"),
        ("No clear AI signals", "suspected", [], "Inconclusive"),
        ("Likely authentic/camera-captured", "no_clear_signals", [], "No clear AI signals"),
        ("Likely AI-generated", "no_clear_signals", [], "Likely AI-generated"),
    ],
)
async def test_local_edit_evidence_is_not_overruled_by_low_global_ai_score(
    classification, local_assessment, observations, expected,
):
    client = AsyncMock()
    client.model = "test-vision"
    client.generate.return_value = json.dumps({
        "classification": classification,
        "confidence": 95,
        "ai_probability": 5,
        "summary": "Scene assessment.",
        "signals": ["Natural lighting."],
        "limitations": "Visual review only.",
        "local_edit_assessment": local_assessment,
        "local_edit_signals": observations,
    })
    result = await GeminiImageDetector(client).analyze(
        PreparedImage(b"test", None, "image/png", 100, 100)
    )
    validated = ImageDetectionResponse.model_validate(result)
    assert validated.classification == expected
    assert validated.score_is_calibrated is False
    assert "does not verify authenticity" in validated.limitations


@pytest.mark.asyncio
@pytest.mark.parametrize("assessment, observations", [
    ("authentic", []), ("suspected", "not a list"), ("suspected", [None]),
])
async def test_invalid_local_review_fails_instead_of_claiming_authenticity(
    assessment, observations,
):
    client = AsyncMock()
    client.generate.return_value = json.dumps({
        "classification": "No clear AI signals", "confidence": 90, "ai_probability": 3,
        "local_edit_assessment": assessment, "local_edit_signals": observations,
    })
    with pytest.raises(ValueError):
        await GeminiImageDetector(client).analyze(
            PreparedImage(b"test", None, "image/png", 100, 100)
        )
