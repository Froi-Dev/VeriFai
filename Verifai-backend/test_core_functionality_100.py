import asyncio
import json
import os
import sys
import time
from pathlib import Path
import httpx

# Ensure backend directory is in path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

from app.Global.db import engine
from sqlalchemy import text
from app.Global.security import hash_password

BASE_URL = "http://127.0.0.1:8000/api/v1"
TEST_USER_EMAIL = "demo.analyst@example.com"
TEST_USER_PASSWORD = "VerifAi2026!Secure"

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def ensure_test_user():
    with engine.begin() as conn:
        pw_hash = hash_password(TEST_USER_PASSWORD)
        exists = conn.execute(text("SELECT user_id FROM users WHERE email = :email"), {"email": TEST_USER_EMAIL}).scalar()
        if exists:
            conn.execute(text("UPDATE users SET password = :pw, email_verified = true, is_active = true WHERE email = :email"), {"pw": pw_hash, "email": TEST_USER_EMAIL})
        else:
            conn.execute(text("INSERT INTO users (username, email, password, email_verified, role, is_active) VALUES ('Demo Analyst', :email, :pw, true, 'user', true)"), {"email": TEST_USER_EMAIL, "pw": pw_hash})

def run_tests():
    print("=" * 80)
    print("VERIFAI CORE FUNCTIONALITY 100% SUITE")
    print("=" * 80)
    
    ensure_test_user()
    
    test_results = []
    
    def log_result(pillar: str, test_name: str, passed: bool, details: str, duration: float):
        test_results.append({
            "pillar": pillar,
            "test_name": test_name,
            "passed": passed,
            "details": details,
            "duration_s": round(duration, 2)
        })
        status_tag = "PASS" if passed else "FAIL"
        print(f"[{status_tag}] [{pillar}] {test_name} ({round(duration, 2)}s)")
        if not passed or "error" in details.lower():
            print(f"       Details: {details}")
        else:
            print(f"       {details}")

    with httpx.Client(base_url=BASE_URL, timeout=120.0) as client:
        # Step 0: Auth Login
        t0 = time.perf_counter()
        login_resp = client.post("/auth/login", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        })
        t_auth = time.perf_counter() - t0
        auth_ok = login_resp.status_code == 200
        log_result("Auth", "User Login & Session Setup", auth_ok, f"Status: {login_resp.status_code}", t_auth)
        if not auth_ok:
            print("Aborting: Could not authenticate.")
            return

        # -------------------------------------------------------------
        # PILLAR 1: Text Analyzer (AI vs Human Detection)
        # -------------------------------------------------------------
        print("\n--- PILLAR 1: Text Analyzer (AI vs Human) ---")
        
        # 1.1 AI-generated Text
        ai_sample = (
            "Furthermore, it is imperative to comprehend that artificial intelligence systems, "
            "particularly large language models, exhibit discernible patterns in syntax, structural "
            "cadence, and statistical vocabulary distribution. These algorithmic manifestations often "
            "lack the idiosyncratic irregularities found within human compositional expressions."
        )
        t0 = time.perf_counter()
        resp = client.post("/detector/text", json={"text": ai_sample})
        dur = time.perf_counter() - t0
        if resp.status_code == 200:
            data = resp.json()
            is_valid = "classification" in data and "confidence" in data and "ai_probability" in data
            log_result("Pillar 1", "AI Text Detection", is_valid, 
                       f"Verdict: {data.get('classification')} (AI Prob: {data.get('ai_probability')}, Conf: {data.get('confidence')})", dur)
        else:
            log_result("Pillar 1", "AI Text Detection", False, f"HTTP {resp.status_code}: {resp.text}", dur)

        # 1.2 Human / Taglish conversational Text
        human_sample = (
            "Kahapon pumunta kami sa palengke para bumili ng bangus at gulay pang sinigang. "
            "Sobrang init ng panahon pero masaya naman kasi kasama ko si Nanay at si bunso. "
            "Pagkauwi, nagluto agad kami habang nanonood ng balita sa TV tungkol sa traffic sa EDSA."
        )
        t0 = time.perf_counter()
        resp = client.post("/detector/text", json={"text": human_sample})
        dur = time.perf_counter() - t0
        if resp.status_code == 200:
            data = resp.json()
            is_valid = "classification" in data and data.get("human_probability", 0) > 0.3
            log_result("Pillar 1", "Human Text Detection", is_valid,
                       f"Verdict: {data.get('classification')} (Human Prob: {data.get('human_probability')}, Conf: {data.get('confidence')})", dur)
        else:
            log_result("Pillar 1", "Human Text Detection", False, f"HTTP {resp.status_code}: {resp.text}", dur)

        # 1.3 Validation boundary check (< 20 chars)
        t0 = time.perf_counter()
        resp = client.post("/detector/text", json={"text": "Too short"})
        dur = time.perf_counter() - t0
        log_result("Pillar 1", "Text Input Validation (<20 chars rejected)", resp.status_code == 422, f"Status: {resp.status_code}", dur)

        # -------------------------------------------------------------
        # PILLAR 2: Media Analyzer (AI Image Detector)
        # -------------------------------------------------------------
        print("\n--- PILLAR 2: Media Analyzer (AI Image Detector) ---")
        fixture_img_path = backend_dir / "tests" / "fixtures" / "image_verification" / "real-doe-nuclear.png"
        if not fixture_img_path.exists():
            fixture_img_path = Path(r"C:\Users\dever\OneDrive\Desktop\News Images Samples\1.png")
            
        if fixture_img_path.exists():
            t0 = time.perf_counter()
            with open(fixture_img_path, "rb") as f:
                resp = client.post("/detector/image", files={"image": (fixture_img_path.name, f, "image/png")})
            dur = time.perf_counter() - t0
            if resp.status_code == 200:
                data = resp.json()
                ok = "classification" in data and "confidence" in data and "signals" in data
                log_result("Pillar 2", "Media AI Image Detection", ok,
                           f"Classification: {data.get('classification')} (Conf: {data.get('confidence')}%, Model: {data.get('model')})", dur)
            else:
                log_result("Pillar 2", "Media AI Image Detection", False, f"HTTP {resp.status_code}: {resp.text}", dur)
        else:
            log_result("Pillar 2", "Media AI Image Detection", False, "Fixture image not found", 0)

        # -------------------------------------------------------------
        # PILLAR 3: Fake News Analyzer (Text Fact-Checking)
        # -------------------------------------------------------------
        print("\n--- PILLAR 3: Fake News Analyzer (Text Fact-Checking) ---")
        
        # 3.1 Real News Claim
        real_claim = "Ferdinand Marcos Jr. signed the Maharlika Investment Fund Act into law."
        t0 = time.perf_counter()
        resp = client.post("/news/verify", json={"text": real_claim})
        dur = time.perf_counter() - t0
        if resp.status_code == 200:
            data = resp.json()
            verdict = data.get("verdict")
            status = data.get("status")
            evidence_count = sum(len(data.get("evidence", {}).get(k, [])) for k in ["supporting", "contradicting", "debunks", "related"])
            ok = status == "SUCCESS" and verdict in ("VERIFIED", "LIKELY_TRUE") and evidence_count > 0
            log_result("Pillar 3", "Fact-Check Real News Claim", ok,
                       f"Status: {status}, Verdict: {verdict}, Confidence: {data.get('confidence')}%, Evidence items: {evidence_count}", dur)
        else:
            log_result("Pillar 3", "Fact-Check Real News Claim", False, f"HTTP {resp.status_code}: {resp.text}", dur)

        # 3.2 Known Debunked / Disinformation Claim
        fake_claim = "Sara Duterte: Trump moves to abolish ICC and order release of Rodrigo Duterte."
        t0 = time.perf_counter()
        resp = client.post("/news/verify", json={"text": fake_claim})
        dur = time.perf_counter() - t0
        if resp.status_code == 200:
            data = resp.json()
            verdict = data.get("verdict")
            status = data.get("status")
            evidence_count = sum(len(data.get("evidence", {}).get(k, [])) for k in ["supporting", "contradicting", "debunks", "related"])
            ok = status == "SUCCESS" and verdict in ("FALSE", "LIKELY_FALSE", "MISLEADING")
            log_result("Pillar 3", "Fact-Check Disinformation Claim", ok,
                       f"Status: {status}, Verdict: {verdict}, Confidence: {data.get('confidence')}%, Evidence items: {evidence_count}", dur)
        else:
            log_result("Pillar 3", "Fact-Check Disinformation Claim", False, f"HTTP {resp.status_code}: {resp.text}", dur)

        # -------------------------------------------------------------
        # PILLAR 4: News Image / Quote Card Fact-Checking (OCR + Verification)
        # -------------------------------------------------------------
        print("\n--- PILLAR 4: News Image Fact-Checking (OCR + Verification) ---")
        sample_img_path = Path(r"C:\Users\dever\OneDrive\Desktop\News Images Samples\1.png")
        if not sample_img_path.exists():
            sample_img_path = backend_dir / "tests" / "fixtures" / "image_verification" / "fake-icc-duterte.png"

        if sample_img_path.exists():
            t0 = time.perf_counter()
            with open(sample_img_path, "rb") as f:
                resp = client.post("/news/verify-image", files={"image": (sample_img_path.name, f, "image/png")})
            dur = time.perf_counter() - t0
            if resp.status_code == 200:
                data = resp.json()
                ocr = data.get("ocr", {})
                extracted = ocr.get("cleaned_text") or ocr.get("raw_text") or data.get("summary") or data.get("reasoning_summary") or ""
                verdict = data.get("overall_verdict")
                classification = data.get("classification")
                ok = bool(extracted.strip()) and (verdict is not None or classification is not None)
                log_result("Pillar 4", "News Image OCR & Fact-Check", ok,
                           f"Extracted: '{extracted[:60]}...', Classification: {classification}, Verdict: {verdict}", dur)
            else:
                log_result("Pillar 4", "News Image OCR & Fact-Check", False, f"HTTP {resp.status_code}: {resp.text}", dur)
        else:
            log_result("Pillar 4", "News Image OCR & Fact-Check", False, "Sample image not found", 0)

        # -------------------------------------------------------------
        # PILLAR 5: Scans & Analytics Persistence
        # -------------------------------------------------------------
        print("\n--- PILLAR 5: Scans & Analytics Persistence ---")
        t0 = time.perf_counter()
        resp = client.get("/scans")
        dur = time.perf_counter() - t0
        if resp.status_code == 200:
            data = resp.json()
            stats = data.get("stats", {})
            items = data.get("items", [])
            total = stats.get("total", 0)
            text_cnt = stats.get("textCount", 0)
            media_cnt = stats.get("mediaCount", 0)
            news_cnt = stats.get("newsCount", 0)
            weekly_total = stats.get("weeklyTotal", 0)
            
            scans_ok = total > 0 and len(items) > 0 and weekly_total > 0
            log_result("Pillar 5", "Fetch Scans & Aggregated Statistics", scans_ok,
                       f"Total Scans: {total} (Text: {text_cnt}, Media: {media_cnt}, News: {news_cnt}, Weekly: {weekly_total})", dur)
            
            # Test Deleting one scan
            if items:
                first_scan = items[0]
                scan_db_id = first_scan["db_id"]
                t0_del = time.perf_counter()
                del_resp = client.delete(f"/scans/{scan_db_id}")
                dur_del = time.perf_counter() - t0_del
                log_result("Pillar 5", "Delete Single Scan Record", del_resp.status_code == 200,
                           f"Deleted scan #{scan_db_id} (Status: {del_resp.status_code})", dur_del)
        else:
            log_result("Pillar 5", "Fetch Scans & Aggregated Statistics", False, f"HTTP {resp.status_code}: {resp.text}", dur)

        # -------------------------------------------------------------
        # PILLAR 6: Guest Public Live Demo Endpoints
        # -------------------------------------------------------------
        print("\n--- PILLAR 6: Guest Public Live Demo Endpoints ---")
        # 6.1 Guest detect text
        t0 = time.perf_counter()
        resp = client.post("/guest/detect-text", json={"text": "Artificial intelligence algorithms can generate coherent text matching user specifications."})
        dur = time.perf_counter() - t0
        if resp.status_code == 200:
            data = resp.json()
            ok = "classification" in data and "confidence" in data
            log_result("Pillar 6", "Guest Text Detection Live Demo", ok,
                       f"Classification: {data.get('classification')}, Confidence: {data.get('confidence')}", dur)
        else:
            log_result("Pillar 6", "Guest Text Detection Live Demo", False, f"HTTP {resp.status_code}: {resp.text}", dur)

        # 6.2 Guest verify news
        t0 = time.perf_counter()
        resp = client.post("/guest/verify-news", json={"text": "Philippine president Ferdinand Marcos Jr. approved new executive orders."})
        dur = time.perf_counter() - t0
        if resp.status_code == 200:
            data = resp.json()
            ok = "verdict" in data and "confidence" in data
            log_result("Pillar 6", "Guest News Verification Live Demo", ok,
                       f"Verdict: {data.get('verdict')}, Confidence: {data.get('confidence')}%", dur)
        else:
            log_result("Pillar 6", "Guest News Verification Live Demo", False, f"HTTP {resp.status_code}: {resp.text}", dur)

    # -------------------------------------------------------------
    # Summary Report & Score Calculation
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print("FINAL CORE FUNCTIONALITY SCORECARD")
    print("=" * 80)
    total_tests = len(test_results)
    passed_tests = sum(1 for r in test_results if r["passed"])
    score_pct = (passed_tests / total_tests) * 100.0 if total_tests > 0 else 0.0

    print(f"Total Tests Executed: {total_tests}")
    print(f"Tests Passed:         {passed_tests}")
    print(f"Tests Failed:         {total_tests - passed_tests}")
    print(f"Core Functionality:   {score_pct:.1f}%")
    print("=" * 80)
    
    # Save results to json
    report_path = backend_dir / "core_functionality_results.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "score_percentage": score_pct,
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "results": test_results
        }, f, indent=2)
    print(f"Detailed scorecard saved to: {report_path}")
    return score_pct

if __name__ == "__main__":
    run_tests()
