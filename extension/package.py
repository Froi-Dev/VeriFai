"""Run python extension/package.py after editing extension sources."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parent
target = root.parent / "verifai-frontend/public/downloads/verifai-extension.zip"
target.parent.mkdir(parents=True, exist_ok=True)
with ZipFile(target, "w", ZIP_DEFLATED) as archive:
    for name in ("manifest.json", "background.js", "bridge.js", "popup.html", "popup.js", "popup.css"):
        archive.write(root / name, name)
print(target)
