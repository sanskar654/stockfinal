# Continuous Market Monitoring & Dynamic Alerts (Co-Pilot)
**Internship Presentation & Technical Overview**

---

## 1. High-Level Overview (For Management)

**The Problem (What it was earlier):**
Earlier, our platform was just a **One-Time Predictor**. A user would click 'Analyze', and the model would give them a target and stop-loss based on that exact second in time. Once they entered the trade, they were on their own. If the market suddenly crashed 10 minutes later, our platform wouldn't warn them. If the stock hit the target and kept booming, they might sell too early and miss out on bigger profits. It was like handing someone a printed map but not giving them a live GPS while they drive.

**The Solution (What we did now):**
We upgraded the platform into a **Continuous Real-Time Co-Pilot**. Now, when a user enters a stock and clicks "Analyze & Activate Live Co-Pilot", our backend automatically starts tracking that specific trade every single minute in the background. 
1. **Locking in Profits (Trailing Stop-Loss):** If the stock goes up, our system dynamically calculates a new stop-loss and moves it higher. So even if the market falls later, their profit is already locked in.
2. **Catching Crashes (Trend Reversal):** If our model detects a sudden shift in momentum, it instantly pushes a live alert to the user's screen telling them to exit immediately to protect their capital. 

Instead of just predicting the entry, we now hold the user's hand throughout the entire lifecycle of the trade.

---

## 2. Technical Architecture Overview (For Engineering/Frontend)

**What it was earlier:**
Previously, the platform was stateless. The frontend made a single `GET /predict/{ticker}` REST call, painted the UI with the JSON response, and that was it. There was no concept of an "active" trade.

**What changed on the Backend:**
- **State Management:** Added a lightweight SQLite database (`trades.db`) to persist active trades. (Unlike our Parquet files which store raw historical ML market data, SQLite acts as the user's live portfolio ledger).
- **Background Daemon:** Built a custom background Python Thread in FastAPI that polls our ML pipeline every 60 seconds for all active trades.
- **No Third-Party Bots:** We aren't using an external Telegram bot or pre-made AI. The Co-Pilot is our own native Python engine pulling from the FYERS API and running our custom ML models.

**Frontend Integration Workflow:**
1. **Single Action Button:** The frontend now has one main button: `"🚀 Analyze Order & Activate Live Co-Pilot"`. Clicking this fetches the prediction and automatically calls the new `POST /api/trades` endpoint to register the trade in the database.
2. **WebSockets for Live Alerts:** The frontend connects to a WebSocket at `ws://<backend-url>/ws/alerts`. Instead of polling the server, the frontend simply listens to this socket. Whenever the 60-second background loop recalculates a trailing stop-loss or detects a trend reversal, it pushes a JSON payload directly through this socket, updating the "Live Co-Pilot Alerts" UI instantly.

---

## 3. A Practical Example: A Day in the Life of a Trade

Here is a step-by-step example of exactly how the platform works in the live market, using **Reliance Industries**.

### 🕥 10:00 AM — The Entry & Activation
You open the platform, type in **RELIANCE**, and click **"🚀 Analyze Order & Activate Live Co-Pilot"**.
*   **What happens:** The ML model runs and says, *"Reliance is at ₹2,500. The trend is Bullish. Buy it! Target is ₹2,520, and Stop-Loss is ₹2,490."*
*   **Behind the scenes:** You buy the stock on your broker (like Groww). Meanwhile, our platform instantly saves this trade in `trades.db` and the background Co-Pilot begins watching Reliance every 60 seconds. 

### 🕚 10:30 AM — The Boom (Locking in Profit)
Reliance is having a great day. The price shoots up from ₹2,500 and crosses your target of ₹2,520. It is now at ₹2,525. 
*   **What happens:** Normally, you would be confused—*should I sell now and take my ₹20 profit, or hold for more?* 
*   **The Co-Pilot steps in:** The Co-Pilot pushes a live **🟢 Green Alert** to your screen: *"Target reached! Trend is still Bullish. HOLD for more profit. Stop-Loss moved up to ₹2,515."*
*   **Why this is huge:** You just locked in a guaranteed ₹15 profit per share. Even if the stock crashes now, you will not lose money.

### 🕛 12:45 PM — The Sudden Market Crash
Some bad news comes out on TV. The entire stock market starts falling rapidly. Reliance drops from ₹2,530 down to ₹2,520 in just a few minutes. 
*   **What happens:** The ML model detects that the momentum indicators (like RSI and MACD) are breaking down. The trend has completely flipped.
*   **The Co-Pilot steps in:** The Co-Pilot immediately pushes a live **🔴 Red Alert** to your screen: *"ALERT: Trend reversed to Bearish. SELL immediately to protect capital."*
*   **Why this is huge:** You sell at ₹2,520. You made a ₹20 profit. If you didn't have the Co-Pilot, you might have held onto the stock hoping it would go back up, and watched it crash all the way back to ₹2,450, turning a winning trade into a loss.

### 🕒 3:15 PM — End of the Day (Market Close)
Let's pretend the crash never happened, and you held a different trade all day long. The time hits 3:15 PM.
*   **What happens:** The Indian stock market closes at 3:30 PM. Since our ML model is designed specifically for **intraday** (same-day) trading, holding stocks overnight is risky.
*   **The Co-Pilot steps in:** The platform automatically sweeps the database, marks your trade as `CLOSED_EOD` (End of Day), and pushes a **🟡 Yellow Alert**: *"Market closing soon. Close all intraday open positions now."*

**Summary:** You don't have to stare at the chart for 5 hours. You just activate the Co-Pilot at 10:00 AM, and it acts as your personal risk manager for the rest of the day.
