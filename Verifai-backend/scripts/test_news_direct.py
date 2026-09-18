import asyncio
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.FakeNewsAnalyzer.news import news_verifier

news_test_cases = [
    {
        "claim": "Rodrigo Duterte was elected President of the Philippines in May 2016.",
        "expected": ["VERIFIED", "LIKELY_TRUE"],
        "category": "True historical fact"
    },
    {
        "claim": "Ferdinand Marcos Jr. is the current President of the Republic of the Philippines as of 2026.",
        "expected": ["VERIFIED", "LIKELY_TRUE"],
        "category": "Current official fact"
    },
    {
        "claim": "The Department of Health declared that drinking boiling salt water immediately cures COVID-19 and kills all viruses in 5 minutes.",
        "expected": ["FALSE", "LIKELY_FALSE", "MISLEADING"],
        "category": "Medical misinformation / debunked hoax"
    },
    {
        "claim": "Pope Francis officially endorsed Rodrigo Duterte during the 2016 Philippine presidential elections and praised his war on drugs.",
        "expected": ["FALSE", "LIKELY_FALSE", "MISLEADING"],
        "category": "Fabricated viral endorsement / debunked"
    },
    {
        "claim": "The Philippine peso became the strongest currency in the entire world, overtaking the US Dollar and British Pound under the Marcos administration.",
        "expected": ["FALSE", "LIKELY_FALSE", "MISLEADING"],
        "category": "Economic disinformation hoax"
    },
    {
        "claim": "Typhoon Yolanda (Haiyan) made landfall in the Philippines in November 2013 causing catastrophic damage in Eastern Visayas.",
        "expected": ["VERIFIED", "LIKELY_TRUE"],
        "category": "Historical disaster fact"
    },
    {
        "claim": "DepEd announced that all students in the Philippines will receive 50,000 pesos monthly allowance from the government starting next week.",
        "expected": ["FALSE", "LIKELY_FALSE", "MISLEADING"],
        "category": "Scam / fake government announcement"
    },
    {
        "claim": "Bongbong Marcos and Sara Duterte won the 2022 Philippine national elections as President and Vice President.",
        "expected": ["VERIFIED", "LIKELY_TRUE"],
        "category": "Electoral fact"
    },
    {
        "claim": "NASA confirmed that the earth will experience 6 days of total complete darkness next month due to solar eclipse.",
        "expected": ["FALSE", "LIKELY_FALSE", "MISLEADING"],
        "category": "Recurring viral hoax"
    },
    {
        "claim": "The Bangko Sentral ng Pilipinas introduced polymer 1000-piso banknotes featuring the Philippine Eagle into circulation.",
        "expected": ["VERIFIED", "LIKELY_TRUE"],
        "category": "Official currency fact"
    }
]

async def test_direct_news_verifier():
    print("=" * 95)
    print("FEATURE 2 BENCHMARK: DIRECT VERIFIER TESTING (BYPASSING HTTP RATE LIMITER)")
    print("=" * 95)
    
    correct = 0
    total = len(news_test_cases)
    
    for idx, item in enumerate(news_test_cases, 1):
        claim = item["claim"]
        expected = item["expected"]
        print(f"\n[{idx:02d}/{total:02d}] Claim: {claim}")
        try:
            res = await news_verifier.verify(claim)
            verdict = res.get("verdict")
            conf = res.get("confidence")
            reasoning = res.get("reasoning", "")[:100]
            is_pass = verdict in expected
            if is_pass:
                correct += 1
            status_flag = "PASS" if is_pass else "FAIL"
            print(f"       -> Result: [{status_flag}] Verdict: {verdict:12s} (Confidence: {conf}%) | Expected: {expected}")
            print(f"          Reasoning: {reasoning}...")
        except Exception as e:
            print(f"       -> [FAIL] Exception: {e}")
            
    acc = (correct / total) * 100
    print("\n" + "=" * 95)
    print(f"FAKE NEWS VERIFIER FINAL BENCHMARK: {correct}/{total} Correct ({acc:.1f}% Accuracy)")
    print("=" * 95)

if __name__ == "__main__":
    asyncio.run(test_direct_news_verifier())
