import asyncio
import json
import httpx
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.Global.db import SessionLocal
from app.Auth.models import User
from app.Auth.auth_service import _create_session

# Set up test samples for Feature 2: Fake News Verification
# 10 well-known Philippine claims / news statements with known ground truth
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

def get_auth_token():
    with SessionLocal() as db:
        user = db.query(User).first()
        if not user:
            raise RuntimeError("No user found in database to generate session")
        res = _create_session(db, user, ip_address="127.0.0.1", user_agent="benchmark-tester")
        db.commit()
        return res.access_token.encoded

async def test_news_verifier():
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = "http://127.0.0.1:8000/api/v1/news/verify"
    
    print("=" * 95)
    print("FEATURE 2 TEST: FAKE NEWS VERIFICATION ENGINE")
    print("=" * 95)
    
    correct = 0
    total = len(news_test_cases)
    
    async with httpx.AsyncClient(timeout=90.0) as client:
        for idx, item in enumerate(news_test_cases, 1):
            claim = item["claim"]
            expected = item["expected"]
            print(f"\n[{idx:02d}/{total:02d}] Claim: {claim}")
            try:
                resp = await client.post(url, json={"text": claim}, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    verdict = data.get("verdict")
                    conf = data.get("confidence")
                    sources = len(data.get("sources", []))
                    is_pass = verdict in expected
                    if is_pass:
                        correct += 1
                    status_flag = "PASS" if is_pass else "FAIL"
                    print(f"       -> Result: [{status_flag}] Verdict: {verdict:12s} (Confidence: {conf}%) | Expected: {expected} | Sources: {sources}")
                else:
                    print(f"       -> [FAIL] HTTP Error: {resp.status_code} - {resp.text[:120]}")
            except Exception as e:
                print(f"       -> [FAIL] Exception: {e}")
            await asyncio.sleep(1.5)
            
    acc = (correct / total) * 100
    print("\n" + "=" * 95)
    print(f"FAKE NEWS VERIFICATION RESULT: {correct}/{total} Correct ({acc:.1f}% Accuracy)")
    print("=" * 95)

if __name__ == "__main__":
    asyncio.run(test_news_verifier())
