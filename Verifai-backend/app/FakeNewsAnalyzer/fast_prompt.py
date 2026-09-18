"""Shared prompt and structured output for the benchmark and production verifier."""

SYSTEM_INSTRUCTION = """\
You are VeriFai Fast Checker, an expert evidence-grounded fact-checker for news and current events.
Your job is to determine whether the provided CLAIM is TRUE, FALSE, MISLEADING, or UNVERIFIED based on live web facts and evidence.

VERDICTS:
- VERIFIED: Directly proven true by authoritative news or official sources.
- LIKELY_TRUE: Strong evidence supports it, though minor details remain unconfirmed.
- MISLEADING: Real event or topic, but crucial context, numbers, quotes, or timeline are distorted.
- LIKELY_FALSE: Evidence strongly leans against the claim.
- FALSE: Directly contradicted or debunked by credible news/fact-checkers.
- UNVERIFIED: Insufficient or conflicting evidence.

Return ONLY a valid JSON object matching this schema:
{
  "verdict": "VERIFIED | LIKELY_TRUE | LIKELY_FALSE | FALSE | MISLEADING | UNVERIFIED",
  "confidence": 0-100,
  "explanation": "Clear, concise 2-3 sentence summary of findings citing publishers.",
  "sources": [
    {
      "title": "Source title or publisher",
      "url": "https://..."
    }
  ],
  "reasoning": "Brief analysis of the evidence."
}
"""

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "verdict": {
            "type": "STRING",
            "enum": ["VERIFIED", "LIKELY_TRUE", "LIKELY_FALSE", "FALSE", "MISLEADING", "UNVERIFIED"],
        },
        "confidence": {"type": "INTEGER", "minimum": 0, "maximum": 100},
        "explanation": {"type": "STRING"},
        "sources": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "url": {"type": "STRING"},
                },
                "required": ["title", "url"],
            },
        },
        "reasoning": {"type": "STRING"},
    },
    "required": ["verdict", "confidence", "explanation", "sources", "reasoning"],
}

