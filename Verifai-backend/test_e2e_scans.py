import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1"

from app.Global.db import engine
from sqlalchemy import text
from app.Global.security import hash_password

# Ensure user exists
with engine.begin() as conn:
    pw_hash = hash_password("VerifAi2026!Secure")
    exists = conn.execute(text("SELECT user_id FROM users WHERE email = 'demo.analyst@example.com'")).scalar()
    if exists:
        conn.execute(text("UPDATE users SET password = :pw, email_verified = true WHERE email = 'demo.analyst@example.com'"), {"pw": pw_hash})
    else:
        conn.execute(text("INSERT INTO users (username, email, password, email_verified, role, is_active) VALUES ('Demo Analyst', 'demo.analyst@example.com', :pw, true, 'user', true)"), {"pw": pw_hash})

with httpx.Client(base_url=BASE_URL, timeout=120.0) as client:
    # 1. Login
    print("1. Logging in...")
    login_resp = client.post("/auth/login", json={
        "email": "demo.analyst@example.com",
        "password": "VerifAi2026!Secure"
    })
    print("Login status:", login_resp.status_code)
    assert login_resp.status_code == 200

    # 2. Get initial scans and stats
    print("\n2. Fetching initial scans...")
    initial_scans = client.get("/scans")
    print("Initial scans status:", initial_scans.status_code)
    initial_data = initial_scans.json()
    print("Initial stats:", initial_data["stats"])
    initial_total = initial_data["stats"]["total"]

    # 3. Perform a text analysis
    print("\n3. Performing text scan...")
    text_to_scan = "Artificial intelligence language models produce sentences with notable patterns, predictable word sequences, and calibrated statistical consistency."
    scan_resp = client.post("/detector/text", json={"text": text_to_scan})
    print("Text scan status:", scan_resp.status_code)
    scan_result = scan_resp.json()
    print("Classification:", scan_result.get("classification"))
    print("Confidence:", scan_result.get("confidence"))
    assert scan_resp.status_code == 200

    # 4. Verify scan is recorded and stats updated
    print("\n4. Verifying scan count and weekly graph stats...")
    updated_scans = client.get("/scans")
    assert updated_scans.status_code == 200
    updated_data = updated_scans.json()
    stats = updated_data["stats"]
    print("Updated stats:", stats)
    assert stats["total"] == initial_total + 1
    assert stats["textCount"] >= 1
    assert stats["weeklyTotal"] >= 1
    today_slot = [s for s in stats["weeklyScans"] if s["isToday"]][0]
    print(f"Today ({today_slot['label']}) scan count in weekly graph:", today_slot["count"])
    assert today_slot["count"] >= 1

    # Verify latest scan in items
    latest_item = updated_data["items"][0]
    print("Latest scan in history:", latest_item["id"], latest_item["name"], latest_item["classification"])
    assert latest_item["kind"] == "text"

    # 5. Perform a news verification
    print("\n5. Performing news verification scan...")
    news_resp = client.post("/news/verify", json={"text": "Philippine government announces nationwide suspension of classes due to super typhoon."})
    print("News scan status:", news_resp.status_code)
    assert news_resp.status_code == 200

    # 6. Verify news scan is recorded
    print("\n6. Verifying updated stats after news scan...")
    final_scans = client.get("/scans")
    assert final_scans.status_code == 200
    final_data = final_scans.json()
    final_stats = final_data["stats"]
    print("Final stats:", final_stats)
    assert final_stats["total"] == initial_total + 2
    assert final_stats["newsCount"] >= 1
    assert final_stats["weeklyTotal"] >= 2

    print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")
