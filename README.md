# Portfolio Monitor — Streamlit + yfinance

Bloomberg-terminal-styled portfolio dashboard with live Yahoo Finance data, Schwab CSV import, blended benchmark, allocation charts, and CTR calculations.

## Deploy to Streamlit Community Cloud (FREE)

### Step 1: Push to GitHub
1. Create a new GitHub repository (e.g., `portfolio-dashboard`)
2. Upload these files to the repo root:
   - `app.py`
   - `requirements.txt`
   - `.streamlit/config.toml` (create the `.streamlit` folder first)

### Step 2: Deploy on Streamlit Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with your GitHub account
3. Click **"New app"**
4. Select your repo, branch `main`, and file `app.py`
5. Click **Deploy**
6. Wait ~2 minutes — your app is live!

Your app URL will be: `https://your-app-name.streamlit.app`

## Features

- **Schwab CSV Import** — upload your transaction history, auto-calculates positions + avg cost
- **Live yfinance data** — real-time prices, no CORS issues, auto-refreshes every 60s
- **Performance chart with period toggles** — INCEP (since 2/2/2026), YTD, 1M, 7D
- **Blended benchmark** — customizable weighted ETF composite (default: 60% SPY / 40% ACWI)
- **Allocation pie charts** — position weights + sleeve split
- **Holdings table** — Day P&L, Total Return, Weight, CTR per position
- **Sleeve breakdowns** — separate ETF and Stock sleeve metrics
- **Rebalance log** — manual entry + auto-populated from CSV import
- **JSON export** — backup your data

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`
