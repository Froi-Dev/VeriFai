"""Batch OCR and Fast Fact-Checking Benchmark for News Images Samples.

Processes images in 'C:\\Users\\dever\\OneDrive\\Desktop\\News Images Samples',
performs Gemini 3.5 Vision OCR, extracts news claims, and runs them through
the ultra-fast verification pipeline to measure speed and accuracy.
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.Global.config import settings
from app.FakeNewsAnalyzer.image_fact_checker import prepare_image, GeminiVisionClient
from fast_news_checker import FastNewsChecker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("batch_ocr_verifier")


def get_primary_claim_from_ocr(ocr_result: dict[str, Any]) -> str:
    """Extract the most relevant news headline/claim from OCR blocks."""
    blocks = ocr_result.get("blocks", [])
    headlines = [b["text"] for b in blocks if b.get("type") == "headline"]
    bodies = [b["text"] for b in blocks if b.get("type") == "body"]

    if headlines:
        # Join multiple headline segments if present
        return " ".join(headlines).strip()
    elif bodies:
        return bodies[0].strip()
    
    raw = ocr_result.get("raw_text", "").strip()
    # Take first 2 sentences or first 200 chars if long
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    return " ".join(lines[:3]) if lines else raw


async def process_image(
    image_path: Path,
    vision_client: GeminiVisionClient,
    verifier: FastNewsChecker,
) -> dict[str, Any]:
    """Process a single image: OCR -> Claim Extraction -> Fact Check."""
    filename = image_path.name
    logger.info(f"Processing {filename}...")
    
    # --- Step 1: Read & Prepare Image ---
    t_start = time.perf_counter()
    image_bytes = image_path.read_bytes()
    prepared = prepare_image(image_bytes, max_pixels=settings.image_ocr_max_pixels)
    
    # --- Step 2: Gemini 3.5 Vision OCR ---
    t_ocr_start = time.perf_counter()
    ocr_result = await vision_client.transcribe_structured(prepared)
    ocr_time = time.perf_counter() - t_ocr_start
    
    raw_ocr_text = ocr_result.get("raw_text", "")
    primary_claim = get_primary_claim_from_ocr(ocr_result)
    if not primary_claim:
        primary_claim = raw_ocr_text[:200]
    
    # --- Step 3: Fast Fact-Check ---
    t_verify_start = time.perf_counter()
    fact_result = await verifier.verify(primary_claim)
    verify_time = time.perf_counter() - t_verify_start
    
    total_time = time.perf_counter() - t_start

    return {
        "filename": filename,
        "image_size_kb": round(len(image_bytes) / 1024, 1),
        "ocr_raw_text": raw_ocr_text,
        "extracted_claim": primary_claim,
        "verdict": fact_result.get("verdict", "UNVERIFIED"),
        "confidence": fact_result.get("confidence", 0),
        "explanation": fact_result.get("explanation", ""),
        "reasoning": fact_result.get("reasoning", ""),
        "sources": fact_result.get("sources", []),
        "timing": {
            "ocr_seconds": round(ocr_time, 2),
            "search_seconds": fact_result.get("search_time_seconds", 0),
            "reasoning_seconds": fact_result.get("gemini_time_seconds", 0),
            "fact_check_seconds": round(verify_time, 2),
            "total_seconds": round(total_time, 2),
        },
    }


async def main() -> None:
    samples_dir = Path(r"C:\Users\dever\OneDrive\Desktop\News Images Samples")
    if not samples_dir.exists():
        print(f"Directory not found: {samples_dir}")
        return

    # Find and sort all image files (1.png, 2.png, ..., 10.png numerically)
    def sort_key(p: Path):
        stem = p.stem
        return int(stem) if stem.isdigit() else stem

    image_files = sorted(
        [p for p in samples_dir.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}],
        key=sort_key,
    )

    print("=" * 80)
    print(f" VeriFai Image OCR & Fast Fact-Checking Benchmark ({len(image_files)} Images)")
    print("=" * 80)
    print(f"Directory: {samples_dir}\n")

    vision_client = GeminiVisionClient(settings)
    verifier = FastNewsChecker(model="gemini-3.5-flash-lite")

    results = []
    for idx, img_path in enumerate(image_files, 1):
        print(f"[{idx}/{len(image_files)}] Analyzing {img_path.name}...")
        try:
            res = await process_image(img_path, vision_client, verifier)
            results.append(res)
            print(f"   -> OCR: \"{res['extracted_claim'][:60]}...\" ({res['timing']['ocr_seconds']}s)")
            print(f"   -> Verdict: {res['verdict']} ({res['confidence']}%) | Total: {res['timing']['total_seconds']}s")
        except Exception as exc:
            logger.error(f"Failed to process {img_path.name}: {exc}", exc_info=True)
            results.append({
                "filename": img_path.name,
                "error": str(exc),
                "timing": {"total_seconds": 0},
            })

    # Save benchmark JSON artifact
    out_file = backend_dir / "benchmark_results.json"
    out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved detailed benchmark data to: {out_file}")

    # Summary Table
    print("\n" + "=" * 90)
    print(f"{'Image':<10} | {'Verdict':<12} | {'Conf':<6} | {'OCR (s)':<8} | {'Check (s)':<10} | {'Total (s)':<10}")
    print("-" * 90)
    
    total_latencies = []
    ocr_latencies = []
    verify_latencies = []
    
    for r in results:
        t = r.get("timing", {})
        total_s = t.get("total_seconds", 0)
        ocr_s = t.get("ocr_seconds", 0)
        chk_s = t.get("fact_check_seconds", 0)
        if total_s > 0:
            total_latencies.append(total_s)
            ocr_latencies.append(ocr_s)
            verify_latencies.append(chk_s)
            
        print(f"{r['filename']:<10} | {r.get('verdict', 'ERR'):<12} | {str(r.get('confidence', '')) + '%':<6} | {ocr_s:<8} | {chk_s:<10} | {total_s:<10}")

    print("=" * 90)
    if total_latencies:
        avg_total = sum(total_latencies) / len(total_latencies)
        avg_ocr = sum(ocr_latencies) / len(ocr_latencies)
        avg_chk = sum(verify_latencies) / len(verify_latencies)
        print(f"Averages:   Total: {avg_total:.2f}s | OCR: {avg_ocr:.2f}s | Fact-Check: {avg_chk:.2f}s")
    print("=" * 90)


if __name__ == "__main__":
    asyncio.run(main())
