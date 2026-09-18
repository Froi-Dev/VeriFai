"""Last-pass wording cleanup for generated explanations, never source quotes."""

import re


def plain_language(text: str) -> str:
    replacements = {
        "compound hoax": "post with several false claims",
        "unsubstantiated": "not backed by evidence",
        "substantiated": "backed by evidence",
        "unilaterally": "on their own",
        "unilateral": "one-sided",
        "modality": "whether something happened or is only possible",
        "dissolution": "closing down",
        "corroborated": "confirmed",
        "corroboration": "confirmation",
    }
    for word, replacement in replacements.items():
        text = re.sub(r"\b" + re.escape(word) + r"\b", replacement, text, flags=re.IGNORECASE)
    return text
