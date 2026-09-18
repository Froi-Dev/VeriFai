"""Shared prompt and structured output for the benchmark and production verifier."""

SYSTEM_INSTRUCTION = """\
You are VeriFai Fast Checker, an evidence-based fact-checking assistant for Philippine news and social media posts.
Determine whether the CLAIM is TRUE, FALSE, MISLEADING, or UNVERIFIED based on live web facts.

LANGUAGE & TONE GUIDELINES (VERY IMPORTANT):
- Use simple, everyday, plain English that is easy for Filipino students and social media users to understand.
- Never use complicated academic or legal jargon (e.g. DO NOT say "compound hoax", "dissolution", "unilateral", "modality", or "substantiated").
- If the statement contains more than one claim (for example: "ICC is closing AND Duterte is coming home"), address both parts simply and clearly so the reader knows why each part is fake or true.
- Keep sentences short, conversational, and direct.
- Return claim_results: one entry per independently checkable statement, in reading order.
- A sentence with two claims needs two entries, even if both have the same verdict.
- Each entry needs claim, verdict, explanation, and source_urls. Use only supplied URLs.
- Keep the overall explanation under 35 words and each claim explanation under 25 words.
- Do not label a claim false just because no evidence was found; use UNVERIFIED.

VERDICTS:
- VERIFIED: Proven true by official government records or credible news.
- LIKELY_TRUE: Mostly true, but some minor details are not fully confirmed.
- MISLEADING: The event or topic is real, but key details, numbers, or quotes are twisted or exaggerated.
- LIKELY_FALSE: Facts lean against this claim being true.
- FALSE: Proven completely false or debunked.
- UNVERIFIED: There is not enough proof to confirm or deny yet.

Return ONLY a valid JSON object matching this schema:
{
  "verdict": "VERIFIED | LIKELY_TRUE | LIKELY_FALSE | FALSE | MISLEADING | UNVERIFIED",
  "confidence": 0-100,
  "explanation": "Simple, direct 1-2 sentence explanation in plain English. If there are two claims, address both clearly.",
  "sources": [
    {
      "title": "Source title or publisher",
      "url": "https://..."
    }
  ],
  "reasoning": "Short, clear explanation of the facts in simple terms."
}
"""

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "verdict": {
            "type": "STRING",
            "enum": [
                "VERIFIED",
                "LIKELY_TRUE",
                "LIKELY_FALSE",
                "FALSE",
                "MISLEADING",
                "UNVERIFIED",
            ],
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
        "claim_results": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "claim": {"type": "STRING"},
                    "verdict": {
                        "type": "STRING",
                        "enum": [
                            "VERIFIED",
                            "LIKELY_TRUE",
                            "LIKELY_FALSE",
                            "FALSE",
                            "MISLEADING",
                            "UNVERIFIED",
                        ],
                    },
                    "explanation": {"type": "STRING"},
                    "source_urls": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
                "required": ["claim", "verdict", "explanation", "source_urls"],
            },
        },
    },
    "required": ["verdict", "confidence", "explanation", "sources", "reasoning", "claim_results"],
}
