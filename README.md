# NIFTY 50 ML Trading Dashboard

This project is a full-stack trading dashboard with:
- React + Vite frontend
- FastAPI backend
- FYERS token integration
- live market watchlist and prediction APIs
- trade history/profile storage in SQLite
- ML model registry for prediction and risk analysis

## 1) Prerequisites

Install these first:

1. Node.js 18+ or 20+
   - Download: https://nodejs.org/
   - Verify:
     ```bash
     node -v
     npm -v
     ```

2. Python 3.10+ or 3.11+
   - Download: https://www.python.org/downloads/
   - Verify:
     ```bash
     python --version
     ```

3. Git
   - Download: https://git-scm.com/

4. Optional but recommended:
   - VS Code
   - Windows Terminal / PowerShell

## 2) Clone the repository

```bash
git clone <your-repository-url>
cd Trade_Stock_Project-main
```

## 3) Create Python virtual environment

From the project root:

### Windows PowerShell
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### macOS/Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 4) Install backend dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r Backend/requirements.txt
```

If you are using the activated venv, this installs everything required for the FastAPI app and FYERS integration.

## 5) Install frontend dependencies

From the project root:

```bash
npm install
npm install --prefix frontend
```

## 6) Configure environment variables

Create a backend environment file from the example:

```bash
copy Backend\env_example Backend\.env
```

Then edit `Backend/.env` and fill in your values:

```env
FYERS_APP_ID=your_fyers_app_id-100
FYERS_SECRET_KEY=your_fyers_secret_key
FYERS_ACCESS_TOKEN=
FYERS_REFRESH_TOKEN=
FYERS_PIN=your_fyers_pin
FYERS_TOTP_KEY=your_base32_totp_secret
```

You can leave `FYERS_ACCESS_TOKEN` and `FYERS_REFRESH_TOKEN` empty if the app should use a fresh login flow.

## 7) Start the app

From the project root:

```bash
npm run dev
```

This starts:
- the FastAPI backend on port 8000
- the Vite frontend on an available port such as 5173, 5174, or 5175

If a stale backend is still running on port 8000, the startup script will attempt to clean it up before launching a fresh instance.

## 8) Open the app in browser

The terminal will print the frontend URL, usually:

```text
http://localhost:5175/
```

If Vite chooses another port because 5173/5174 are busy, use the port shown in the terminal output.

## 9) Useful commands

### Backend only
```bash
cd Backend
python -m uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend only
```bash
npm run dev --prefix frontend
```

### Build frontend
```bash
npm run build
```

## 10) Notes

- The backend stores trade profile history in SQLite at `Backend/data/trades.db`.
- The backend also keeps FYERS tokens in `Backend/data/live/fyers_tokens.json`.
- Some frontend pages rely on real-time data and may display demo/seed data when market is closed or when no live feed is available.
- If you see a port conflict on 8000, stop the stale process and rerun `npm run dev`.

## 11) Troubleshooting

### Port 8000 already in use
Run:

```powershell
Get-NetTCPConnection -LocalPort 8000
```

Then stop the offending process if needed.

### Frontend shows connection refused
Make sure the backend is running and healthy:

```bash
curl http://127.0.0.1:8000/health
```

Expected result:

```json
{"status":"healthy", ...}
```

### FYERS login fails
Check your credentials in `Backend/.env` and confirm the app is not using a stale token.
