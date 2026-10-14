"""Package the built extension for the website; run npm run build first."""
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, default=root.parent / "verifai-frontend/public/downloads/verifai-extension.zip")
args = parser.parse_args()
dist = root / "dist"
if not (dist / "manifest.json").is_file():
    raise SystemExit("Build verifai-extension first with npm ci and npm run build.")
args.output.parent.mkdir(parents=True, exist_ok=True)
with ZipFile(args.output, "w", ZIP_DEFLATED) as archive:
    for file in sorted(dist.rglob("*")):
        if file.is_file():
            archive.write(file, file.relative_to(dist).as_posix())
print(f"Packaged extension: {args.output}")
