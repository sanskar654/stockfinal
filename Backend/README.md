# 📈 NIFTY 50 ML Trading Guidance Platform — Backend

> **For Frontend Developers**: This is the complete backend API. Your frontend just calls the REST endpoints and connects to the WebSocket. End users of the platform **do not need a Fyers account** — the backend handles all market data internally.

---

## 📌 What This Project Is

This is the **backend (Python/FastAPI) for a retail trading guidance platform**. The platform helps everyday investors make better intraday trading decisions on NIFTY 50 stocks using Machine Learning.

**How it works end-to-end:**

```
[FYERS Stock Exchange API]
         ↓  (live market data, operator's connection)
[This Backend — Python/FastAPI]
  • Fetches real-time NIFTY 50 prices via FYERS API
  • Runs ML models → predicts next 30-min return & direction
  • Applies institutional risk management rules
  • Monitors active trades every 60 seconds (Co-Pilot)
  • Pushes live alerts via WebSocket
         ↓  (REST API + WebSocket)
[Frontend — to be built by frontend developer]
  • Shows predictions, stop-loss, targets to user
  • Displays live Co-Pilot alerts in real-time
         ↓  (website/app)
[End User — retail trader seeking guidance]
  • Gets AI-powered trade guidance on what to buy/sell
  • Receives live alerts if market moves against their trade
  • Does NOT need a Fyers account — the platform handles everything
```

**Who needs a Fyers account?**
| Role | Fyers Account Needed? | Why |
|---|---|---|
| **Operator** (person running the server) | ✅ Yes | To connect to Fyers API and fetch live market data |
| **Frontend Developer** | ❌ No | Just builds UI, calls this backend's REST/WebSocket APIs |
| **End User / Customer** | ❌ No | They use the platform for guidance — backend fetches data on their behalf |

---



## 🚀 Key Features

### 🤖 Real-Time Co-Pilot
- **Continuous Trade Monitoring**: After entering a trade, a background Python thread polls the ML pipeline every 60 seconds for all active trades.
- **Trailing Stop-Loss**: As price rises, the Co-Pilot automatically moves up the stop-loss to lock in profits.
- **Trend Reversal Alerts**: If RSI/MACD momentum breaks down, a live 🔴 Red Alert is pushed instantly via WebSocket: *"ALERT: Trend reversed to Bearish. SELL immediately."*
- **End-of-Day Auto-Close**: At 3:15 PM IST, all intraday open positions are automatically marked `CLOSED_EOD` with a 🟡 Yellow Alert.
- **Live SQLite Portfolio Ledger**: Active trades persisted in `data/trades.db`. Unlike Parquet files (historical ML data), SQLite acts as the real-time portfolio ledger.
- **Native WebSocket Alerts**: No Telegram bots — pure Python WebSocket (`ws://<backend>/ws/alerts`) pushing JSON payloads directly to frontend.

### 🔐 FYERS Authentication Engine
- **Automatic Token Renewal**: Refreshes expired access tokens silently using `grant_type="refresh_token"` — no manual login on daily restarts.
- **Server-Side Token Store**: Tokens saved in `data/live/fyers_tokens.json` (excluded from git).
- **Auth State Machine**: Reports `FYERS_AUTHENTICATED`, `FYERS_TOKEN_EXPIRED`, `FYERS_REAUTH_REQUIRED`, `FYERS_AUTH_ERROR` — never leaks secrets.
- **Login Frequency**: Manual OAuth login required only **once every ~14 days**. Daily restarts auto-reconnect silently.

### 📊 Institutional Risk Management
- **Dynamic ATR Stop-Loss & Target**: Volatility-adjusted (1.5 × ATR₁₄), Risk/Reward Guard ≥ 1:1.4 (else overrides to `"WAIT"`).
- **Dynamic Position Sizing**: 🟢 100% Full / 🟡 50% Reduced / 🔴 0% Do Not Trade.
- **Key Levels & Pullback Guard**: 20-candle Support/Resistance — prevents buying near peak resistance.
- **Volume Strength & Confluence**: Volume confirmation (> 1.1×), RSI Overbought (> 75) / Oversold (< 25) alerts.

### 🧠 ML Models
- **Model B (Regressor)**: MAE `1.51%`, RMSE `2.03%`, Directional Accuracy **`54.56%`**
- **Model C (Classifier)**: Accuracy `53.96%`, Recall **`70.27%`**, F1 `0.6115`, ROC-AUC `0.5545`
- **~46 Scale-Invariant Features**: RSI, MACD, EMA, Bollinger Bands, ATR, ADX, lag periods, rolling windows — zero price-scale leakage.
- **15-minute candles, 2-bar horizon** → 30-minute trend prediction.
- **Automated Self-Retraining**: Scheduled at 6:00 PM weekdays. Promotes new models only if walk-forward CV metrics beat the champion.

---

## 📁 Project Structure

```
├── api/
│   └── app.py                  # FastAPI app — REST endpoints + WebSocket + Co-Pilot background thread
├── config/
│   ├── settings.py             # Central config reader (YAML + .env)
│   └── settings.yaml           # Model/data/feature parameters
├── data/
│   ├── loader.py               # Data loading utilities
│   ├── trades.db               # SQLite — live active trade portfolio ledger
│   ├── live/                   # Per-ticker live Parquet buffers (FYERS streaming)
│   └── raw/
│       └── NIFTY50_Preprocessed.csv  # Historical training dataset
├── features/
│   ├── build_features.py       # Feature engineering pipeline (~46 indicators)
│   └── technical_indicators.py # RSI, MACD, EMA, ATR, ADX, Bollinger Bands
├── inference/
│   ├── predictor.py            # ML inference — loads champion models, runs prediction
│   ├── live_pipeline.py        # Live data → features → prediction pipeline
│   ├── fyers_client.py         # FYERS API v3 market data client
│   ├── monitoring.py           # Co-Pilot monitoring engine
│   └── ticker_utils.py         # NIFTY 50 ticker symbol utilities
4. **Create a `.env` file** inside the `Backend` directory (next to `env_example`):
│   └── registry/               # Versioned champion model store (joblib + metadata JSON)
│       ├── direction_classifier/
    cp Backend/env_example Backend/.env
├── retraining/
│   ├── retrain_job.py          # Retrain pipeline + champion promotion gate
│   ├── drift_monitor.py        # Model drift detection
│   └── scheduler.py            # APScheduler — triggers retrain at 6 PM weekdays
    Copy-Item Backend/env_example Backend/.env
├── services/
│   ├── fyers_auth.py           # FYERS token manager + auto-refresh state machine
│   ├── fyers_market_data.py    # Real-time NIFTY 50 market data service
│   └── trade_tracker.py        # SQLite trade CRUD operations
├── tests/                      # Unit & integration test suite (pytest)
├── training/
│   ├── data_prep.py            # Training data preparation
│   ├── build_targets.py        # Target variable construction
│   ├── train_classifier.py     # Model C (XGBoost Classifier) training
│   ├── train_regressor.py      # Model B (XGBoost Regressor) training
│   └── validation.py           # Walk-forward cross-validation
├── utils/
│   └── model_io.py             # Model save/load with versioning
├── copilot_presentation.md     # Co-Pilot feature — management & technical overview
├── requirements.txt
├── Dockerfile
└── .env                        # (NOT in git) FYERS_APP_ID, FYERS_SECRET_KEY
```

---

## ⚙️ Setup & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/sanskar654/Nifty50-stock-task.git
cd Nifty50-stock-task
```

### 2. Create Virtual Environment & Install Dependencies
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Get Your Own FYERS API Credentials

> ⚠️ **Important:** Every user must create their own Fyers API app. You **cannot** use someone else's `FYERS_APP_ID` or `FYERS_SECRET_KEY` — they are tied to your personal Fyers trading account.

Follow these steps to get your credentials:

1. **Log in to Fyers API Dashboard**: Go to [https://myapi.fyers.in/](https://myapi.fyers.in/) and log in with your Fyers trading account.

2. **Create a New App**:
   - Click **"Create App"**
   - App Name: anything (e.g., `MyTradingBot`)
   - App Type: **Trading Platform**
   - Redirect URL: `http://127.0.0.1:8000/fyers/callback` ← **must match exactly**
   - Click **Save**

3. **Copy your credentials**:
   - **App ID** → looks like `XXXXXXXXXX-100`
   - **Secret Key** → a 10-character string

4. **Create a `.env` file** in the project root directory:
Copy `env_example` to `.env` and replace the placeholder values with your own credentials:
```bash
cp env_example .env
```

On Windows PowerShell, use:
```powershell
Copy-Item env_example .env
```

Then edit `.env`:
```env
FYERS_APP_ID=XXXXXXXXXX-100
FYERS_SECRET_KEY=XXXXXXXXXX
```
> ⚠️ **Never commit `.env` to GitHub.** It contains your personal secret keys and must stay private.

### 4. Run the FastAPI Server
```bash
python -m uvicorn api.app:app --host 127.0.0.1 --port 8000 --reload
```

### 5. One-Time FYERS Login (First Time Only)
Open your browser and go to:
```
http://127.0.0.1:8000/fyers/login
```
- This opens the official FYERS OAuth login page.
- Log in with your **Fyers trading account** (the same account linked to your API app).
- After login, you are redirected back automatically — tokens are saved server-side.
- ✅ **You do NOT need to do this again tomorrow.** The server auto-refreshes your access token daily.
- ⚠️ Manual login is only needed once every **~14 days** when the refresh token expires.

---

## 🌐 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Live dashboard |
| `GET` | `/health` | System health & connection status |
| `GET` | `/fyers/login` | One-click FYERS OAuth login |
| `GET` | `/api/market/nifty50` | Real-time NIFTY 50 market summary |
| `GET` | `/predict/{ticker}` | Single ticker prediction + risk analytics |
| `GET` | `/predict?tickers=WIPRO,TCS` | Batch predictions |
| `POST` | `/api/trades` | Register active trade for Co-Pilot monitoring |
| `GET` | `/api/trades` | List all active trades |
| `WS` | `/ws/alerts` | WebSocket — live Co-Pilot alerts stream |
| `POST` | `/retrain` | Trigger manual model retraining |

---

## 🧪 Run Tests
```bash
python -m pytest tests/test_features.py tests/test_pipeline.py tests/test_ticker_utils.py tests/test_fyers_auth.py -v
```

---

## 🔄 Authentication Flow

```
FIRST TIME:
  /fyers/login → FYERS OAuth → saves access_token + refresh_token server-side

EVERY SUBSEQUENT STARTUP (automatic):
  Load tokens → access_token valid? → ✅ Connected
                           ↓ expired?
               Use refresh_token → auto-renew → ✅ Connected
                           ↓ refresh also expired? (~14 days)
               Manual login → /fyers/login
```

---

## 🐳 Docker
```bash
docker build -t trading-ml .
docker run -p 8000:8000 --env-file .env trading-ml
```

---

## 📝 Important Notes
- `.env` and `data/live/fyers_tokens.json` are excluded from git (security).
- `venv/` is excluded — run `pip install -r requirements.txt` after cloning.
- Models are versioned in `models/registry/` with champion promotion gate.
- The Co-Pilot runs as a background daemon thread inside FastAPI — no separate process needed.
- See `copilot_presentation.md` for a detailed Co-Pilot feature walkthrough with a real trading example.

---

## 🚀 Key Features

1. **Automatic FYERS Token Authentication & Refresh Engine**:
   - **Server-Side Token Store**: Securely stores `access_token` and `refresh_token` in `data/live/fyers_tokens.json` (server-side only, excluded from git).
   - **Automatic Token Renewal**: Automatically refreshes expired access tokens using the official FYERS API v3 refresh-token mechanism (`grant_type="refresh_token"`) without requiring manual user logins on application restarts or runtime token expiration.
   - **Authentication State Machine**: Exposes safe statuses (`FYERS_AUTHENTICATED`, `FYERS_TOKEN_EXPIRED`, `FYERS_REAUTH_REQUIRED`, `FYERS_AUTH_ERROR`) without leaking secret keys or tokens.
2. **Indian Stock Market Hours Engine (`Asia/Kolkata`)**:
   - Timezone-aware market state calculation: `PRE_MARKET` (09:00 - 09:15 IST), `OPEN` (09:15 - 15:30 IST, Mon-Fri), `CLOSED` (After-hours / Weekends).
   - Optimizes polling/streaming intervals to prevent unnecessary API requests when the market is closed.
3. **Backend Real-Time Market Data API (`GET /api/market/nifty50`)**:
   - Serves real-time NIFTY 50 market summary (`symbol`, `price`, `change`, `change_percent`, `timestamp`, `market_status`, `auth_status`) to the frontend.
4. **4 Core Institutional Risk Management Features**:
   - **Dynamic ATR Stop-Loss & Target**: Volatility-adjusted stop loss ($1.5 \times \text{ATR}_{14}$) and Risk/Reward Guard (requires $\ge 1:1.4$ ratio, otherwise overrides to `"WAIT"`).
   - **Dynamic Position Sizing**: Capital protection allocation (🟢 100% Full, 🟡 50% Reduced Risk, 🔴 0% Do Not Trade).
   - **Key Levels & Pullback Guard**: 20-candle Support/Resistance entry zones (prevents buying near peak resistance).
   - **Volume Strength & Confluence**: Volume confirmation ($> 1.1x$) and RSI Overbought ($> 75$) / Oversold ($< 25$) alerts.
5. **Scale-Invariant Feature Engineering**: Computes ~46 normalized technical indicators, ratios, and bounded oscillators (grouped strictly by `Ticker`) to ensure zero price-scale leakage and cross-ticker generalization.
6. **30-Minute Intraday Horizons**: Configured for 15-minute candles (`interval: "15m"`) and 2-bar horizon (`horizon_candles: 2`), predicting 30-minute trend returns.
7. **Automated Self-Retraining & Champion Promotion Gate**: Periodically retrains models on accumulated dataset + live Fyers Parquet buffers (`data/live/*.parquet`), promoting candidates only if walk-forward CV metrics improve upon the current champion.

---

## 🔑 Environment Configuration (`.env`)

Create a `.env` file inside the `ml_service/` directory (or configure environment variables in your deployment system):

```bash
# ml_service/.env
FYERS_APP_ID=YOUR_APP_ID-100       # e.g., QMRW5E4JPC-100
FYERS_SECRET_KEY=YOUR_SECRET_KEY   # e.g., W8ZNTCC6FF
```

> **Security Note**: Never commit `.env` or `data/live/fyers_tokens.json` to GitHub. Ensure `.gitignore` is present. API secret keys and refresh tokens are strictly kept server-side and are NEVER sent to the frontend.

---

## 🔐 Authentication Lifecycle & Workflow

```text
                 INITIAL ONE-TIME LOGIN
                           │
                           ↓
             User opens /fyers/login once
                           │
                           ↓
              Completes FYERS OAuth login
                           │
                           ↓
         Backend exchanges auth_code for tokens
                           │
                           ↓
      Saves access_token & refresh_token server-side
                (data/live/fyers_tokens.json)
                           │
                           ↓
               SUBSEQUENT APP STARTUPS
                     (100% Auto)
                           │
                           ↓
            Backend loads server-side tokens
                           │
                 ┌─────────┴─────────┐
                 │                   │
            Token Valid        Token Expired
                 │                   │
                 │            Auto-Refresh via
                 │            FYERS API v3
                 │                   │
                 └─────────┬─────────┘
                           ↓
                Connects to FYERS &
              Streams Real-Time Data
```

---

## 🛠️ Installation & Setup

1. **Activate Python Virtual Environment & Install Dependencies**:
   ```bash
   cd ml_service
   pip install -r requirements.txt
   ```

2. **Run Comprehensive 9/9 Unit & Integration Test Suite**:
   ```bash
   python -m pytest tests/test_features.py tests/test_pipeline.py tests/test_ticker_utils.py tests/test_fyers_auth.py -v
   ```

---

## 📊 Model Architecture & Performance Metrics

| Model Component | Objective / Metric | 5-Fold Walk-Forward Champion Score |
|---|---|---|
| **Model B (Regressor)** | Avg MAE (Mean Absolute Error) | `1.51399%` |
| **Model B (Regressor)** | Avg RMSE (Root Mean Sq Error) | `2.02870%` |
| **Model B (Regressor)** | Directional Accuracy | **`54.56%`** |
| **Model C (Classifier)** | Avg Accuracy | `53.96%` |
| **Model C (Classifier)** | Avg Precision | `54.23%` |
| **Model C (Classifier)** | Avg Recall | **`70.27%`** |
| **Model C (Classifier)** | Avg F1-Score | `0.6115` |
| **Model C (Classifier)** | Avg ROC-AUC | `0.5545` |

---

## 🌐 Running the FastAPI Inference Service

Start the live FastAPI uvicorn server:

```bash
python -m uvicorn api.app:app --host 127.0.0.1 --port 8000 --reload
```

- **Live Dashboard**: Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser.
- **NIFTY 50 Real-Time Market Data**: `GET http://127.0.0.1:8000/api/market/nifty50`
- **Single Ticker Prediction & Risk Analytics**: `GET http://127.0.0.1:8000/predict/WIPRO`
- **Batch Predictions**: `GET http://127.0.0.1:8000/predict?tickers=WIPRO,RELIANCE,TCS,ADANIENT`
- **System Health & Connection Status**: `GET http://127.0.0.1:8000/health`
- **Initial 1-Click FYERS Authorization**: `GET http://127.0.0.1:8000/fyers/login`

---

## 🔄 Automated Retraining & Model Promotion

The service retrains itself unattended via `retraining/retrain_job.py`:

1. **Trigger**: Scheduled via `retraining/scheduler.py` (APScheduler running at 6:00 PM weekdays after Indian market close) or triggered via `POST /retrain`.
2. **Data Ingestion**: Merges historical dataset with accumulated Fyers live buffers (`data/live/*.parquet`).
3. **Promotion Gate**: Evaluates candidates against champion metadata. Promotes new candidates **only** if metrics improve upon champion scores.
