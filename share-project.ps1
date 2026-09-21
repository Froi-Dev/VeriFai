# 1. Kill any existing cloudflared instance
Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue | Stop-Process -Force

# 2. Start Backend (Hidden in background)
Start-Process .\Verifai-backend\.venv\Scripts\python.exe -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload" -WorkingDirectory .\Verifai-backend -WindowStyle Hidden

# 3. Start Cloudflare Tunnel (Forced HTTP/2 so it works across mobile hotspots, school, office & home Wi-Fi)
$cloudflared = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
if (Test-Path $cloudflared) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$cloudflared' tunnel --protocol http2 --url http://localhost:5173"
}

# 4. Start Frontend
npm --prefix .\verifai-frontend run dev
