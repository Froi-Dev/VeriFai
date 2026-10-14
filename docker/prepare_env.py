"""Create private Docker settings without printing credentials. Standard library only."""
import argparse
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--copy-shared-keys", action="store_true", help="Copy provider settings from Verifai-backend/.env")
args = parser.parse_args()
target = ROOT / ".env"
if target.exists():
    raise SystemExit("Root .env already exists; left unchanged. Edit it directly if needed.")

values = {
    "POSTGRES_PASSWORD": secrets.token_hex(24),
    "JWT_SECRET": secrets.token_hex(32),
    "GEMINI_API_KEYS": "",
    "GEMINI_TEXT_DETECTION_MODEL": "gemini-3.5-flash-lite",
    "GEMINI_VISION_MODEL": "gemini-3.5-flash-lite",
    "NEWS_FAST_MODEL": "gemini-3.5-flash-lite",
    "SERPER_API_KEYS": "",
    "SEARCHAPI_API_KEY": "",
    "NEWS_SEARCH_PROVIDER_ORDER": "serper,searchapi,google",
}
allowed = {
    "GEMINI_API_KEYS", "GEMINI_API_KEY", "GEMINI_TEXT_DETECTION_MODEL",
    "GEMINI_VISION_MODEL", "GEMINI_ADJUDICATOR_MODEL", "NEWS_FAST_MODEL",
    "SERPER_API_KEYS", "SERPER_API_KEY", "SEARCHAPI_API_KEY",
    "SEARCHAPI_AI_MODE_API_KEY", "GOOGLE_SEARCH_API_KEY", "GOOGLE_CSE_ID",
    "NEWS_SEARCH_PROVIDER_ORDER",
}
if args.copy_shared_keys:
    source = ROOT / "Verifai-backend" / ".env"
    for line in source.read_text(encoding="utf-8-sig").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() in allowed:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key.strip()] = value

# Single-quoted Compose values keep dollar signs literal.
def quote(value):
    return "'" + value.replace("'", "\\'") + "'"

with target.open("x", encoding="utf-8", newline="\n") as output:
    output.write("# Private Docker runtime settings. Share only with authorized team members.\n")
    for key, value in values.items():
        output.write(f"{key}={quote(value)}\n")
try:
    target.chmod(0o600)
except OSError:
    pass
print("Created private root .env; provider values were not printed.")
