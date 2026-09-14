import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(r"c:\Users\dever\OneDrive\Desktop\Verifai\Verifai-backend")
sys.path.insert(0, str(backend_dir))

from app.Global.config import settings
from app.FakeNewsAnalyzer.image_fact_checker import PhilippineImageFactChecker

async def run_tests():
    sample_dir = Path(r"C:\Users\dever\OneDrive\Desktop\News Images Samples")
    image_files = sorted(
        sample_dir.glob("*.png"),
        key=lambda p: int(p.stem) if p.stem.isdigit() else 999
    )
    print(f"Found {len(image_files)} sample images in {sample_dir}\n")

    checker = PhilippineImageFactChecker(settings)

    results = []

    for img_path in image_files:
        print("=" * 60)
        print(f"TESTING: {img_path.name} ({img_path.stat().st_size} bytes)")
        print("=" * 60)

        with open(img_path, "rb") as f:
            image_bytes = f.read()

        t0 = time.perf_counter()
        try:
            res = await checker.analyze(image_bytes)
            elapsed = round(time.perf_counter() - t0, 2)

            ocr = res.get("ocr", {})
            verif = res.get("verification") or {}
            timing = res.get("metadata", {}).get("timing", {})

            item = {
                "file": img_path.name,
                "status": res.get("status"),
                "classification": res.get("classification"),
                "confidence": res.get("confidence"),
                "overall_verdict": res.get("overall_verdict"),
                "ocr_provider": ocr.get("provider"),
                "cleaned_text": ocr.get("cleaned_text", ""),
                "summary": res.get("reasoning_summary", ""),
                "elapsed_sec": elapsed,
                "timing": timing,
            }
            results.append(item)

            print(f"Status:         {res.get('status')}")
            print(f"Classification: {res.get('classification')}")
            print(f"Confidence:     {res.get('confidence')}%")
            print(f"Overall Verdict:{res.get('overall_verdict')}")
            print(f"OCR Provider:   {ocr.get('provider')}")
            print(f"Extracted Text: {ocr.get('cleaned_text')[:300]}")
            print(f"Summary:        {res.get('reasoning_summary')[:300]}")
            print(f"Timing:         OCR={timing.get('gemini_ocr_ms')}ms, Verif={timing.get('verification_ms')}ms, Total={timing.get('total_ms')}ms")
            print(f"Wall Clock:     {elapsed}s\n")
        except Exception as exc:
            print(f"ERROR: {exc}\n")
            import traceback
            traceback.print_exc()
            results.append({"file": img_path.name, "error": str(exc)})

    # Write summary to JSON
    out_file = backend_dir / "sample_images_test_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nAll tests completed! Saved details to {out_file}")

if __name__ == "__main__":
    asyncio.run(run_tests())
