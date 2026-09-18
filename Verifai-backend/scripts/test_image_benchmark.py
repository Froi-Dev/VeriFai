import asyncio
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.FakeNewsAnalyzer.image_fact_checker import (
    GeminiImageDetector,
    PhilippineImageFactChecker,
    prepare_image
)
from app.FakeNewsAnalyzer.news import news_verifier, image_fact_checker
from app.ContentDetector.detector import image_detector
from app.Global.config import settings

# Test cases for Media Detection (/detector/image) & Image Fact Check (/news/verify-image)
# Using real fixtures located in tests/fixtures/image_verification and public test assets
FIXTURES_DIR = BACKEND_DIR / "tests" / "fixtures" / "image_verification"

async def test_image_fact_check():
    print("=" * 95)
    print("FEATURE 3 TEST: IMAGE FACT CHECKING & MEDIA ANALYSIS")
    print("=" * 95)
    
    test_images = [
        {
            "path": FIXTURES_DIR / "fake-icc-duterte.png",
            "name": "Fake ICC Dismantle Meme (Sir Jack Argota)",
            "expected_verdict": ["FAKE", "MISLEADING", "UNVERIFIED"],
            "expected_media_ai": ["Likely AI-generated", "Manipulation suspected", "Likely authentic/camera-captured"] # Meme/photo edit
        },
        {
            "path": FIXTURES_DIR / "real-doe-nuclear.png",
            "name": "Real News Graphic - DOE Nuclear Energy Preparations",
            "expected_verdict": ["REAL", "LIKELY_TRUE", "SUPPORTED"],
            "expected_media_ai": ["Likely authentic/camera-captured", "Likely AI-generated", "Manipulation suspected"]
        },
        {
            "path": FIXTURES_DIR / "quote-sara-duterte.png",
            "name": "Attributed Quote Card - VP Sara Duterte",
            "expected_verdict": ["REAL", "LIKELY_TRUE", "MISLEADING", "UNVERIFIED"],
            "expected_media_ai": ["Likely authentic/camera-captured"]
        }
    ]

    total_ocr_fact_checks = 0
    correct_fact_checks = 0
    
    for item in test_images:
        path = item["path"]
        name = item["name"]
        print(f"\nEvaluating Image: {name}")
        print(f"File: {path.name} (exists: {path.exists()})")
        if not path.exists():
            print("  Skipping: File not found")
            continue
            
        with open(path, "rb") as f:
            image_bytes = f.read()
            
        prepared = prepare_image(image_bytes, max_pixels=settings.image_ocr_max_pixels)
        
        # Test 1: Media Authenticity Scan (/detector/image)
        try:
            media_res = await image_detector.analyze(prepared)
            print(f"  [1. Media Detector /detector/image]")
            print(f"      Classification: {media_res.get('classification')}")
            print(f"      AI Prob: {media_res.get('ai_probability')}% | Conf: {media_res.get('confidence')}%")
            print(f"      Signals: {media_res.get('signals')}")
        except Exception as e:
            print(f"  [1. Media Detector ERROR]: {e}")
            
        # Test 2: Image News Fact Checking (/news/verify-image)
        total_ocr_fact_checks += 1
        try:
            fact_res = await image_fact_checker.analyze(image_bytes)
            classification = fact_res.get("classification")
            confidence = fact_res.get("confidence")
            ocr_text = fact_res.get("ocr", {}).get("cleaned_text", "")[:80]
            expected = item["expected_verdict"]
            is_pass = classification in expected or fact_res.get("overall_verdict") in expected
            if is_pass:
                correct_fact_checks += 1
            pass_str = "PASS" if is_pass else "FAIL"
            print(f"  [2. Image News Verifier /news/verify-image]")
            print(f"      [{pass_str}] Classification: {classification} (Conf: {confidence}%)")
            print(f"      OCR Extracted: \"{ocr_text}...\"")
            print(f"      Expected: {expected}")
        except Exception as e:
            print(f"  [2. Image News Verifier ERROR]: {e}")
            
    if total_ocr_fact_checks > 0:
        accuracy = (correct_fact_checks / total_ocr_fact_checks) * 100
        print("\n" + "=" * 95)
        print(f"IMAGE FACT CHECK RESULTS: {correct_fact_checks}/{total_ocr_fact_checks} Pass ({accuracy:.1f}%)")
        print("=" * 95)

if __name__ == "__main__":
    asyncio.run(test_image_fact_check())
