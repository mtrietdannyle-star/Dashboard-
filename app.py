import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta, timezone
import json
import io

# Eastern timezone (UTC-4 EDT / UTC-5 EST)
ET_OFFSET = timedelta(hours=-4)  # EDT
def now_eastern():
    return datetime.now(timezone.utc) + ET_OFFSET

# ════════════════════════════════════════════════════
# PAGE CONFIG
# ════════════════════════════════════════════════════
st.set_page_config(
    page_title="Portfolio Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Bloomberg-style dark theme
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap');
    .stApp { background-color: #000000; }
    header[data-testid="stHeader"] { background-color: #1a1a1a; border-bottom: 1px solid #cc7000; }
    .block-container { padding: 1rem 1.5rem; max-width: 1600px; }
    h1, h2, h3, h4 { color: #ff8c00 !important; font-family: 'Helvetica Neue', Helvetica, sans-serif !important; letter-spacing: 0.05em; }
    p, span, label, .stMarkdown { color: #e8e8e8 !important; font-family: 'Helvetica Neue', Helvetica, sans-serif !important; }
    .stMetric label { color: #555 !important; font-size: 11px !important; text-transform: uppercase; letter-spacing: 0.08em; }
    .stMetric [data-testid="stMetricValue"] { font-size: 22px !important; font-weight: 700 !important; }
    div[data-testid="stMetricDelta"] { font-size: 12px !important; }
    .stDataFrame { border: 1px solid #222 !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 0; background-color: #1a1a1a; border-bottom: 1px solid #333; }
    .stTabs [data-baseweb="tab"] { color: #555; font-weight: 700; text-transform: uppercase; font-size: 11px; letter-spacing: 0.06em; padding: 8px 16px; }
    .stTabs [aria-selected="true"] { color: #ff8c00 !important; border-bottom: 2px solid #ff8c00; }
    .stFileUploader { border: 2px dashed #333 !important; background: #0a0a0a !important; }
    .stFileUploader:hover { border-color: #ff8c00 !important; }
    .stButton > button { background-color: #1a1a1a !important; color: #999 !important; border: 1px solid #333 !important; font-weight: 700 !important; text-transform: uppercase; letter-spacing: 0.06em; font-size: 11px !important; }
    .stButton > button:hover { background-color: #333 !important; color: #ff8c00 !important; border-color: #cc7000 !important; }
    .stSelectbox, .stMultiSelect { background-color: #111 !important; }
    div[data-testid="stExpander"] { border: 1px solid #222 !important; background: #111 !important; }
    div[data-testid="stExpander"] summary { color: #ff8c00 !important; }
    .green { color: #00d26a; } .red { color: #ff3b3b; }
    .metric-card { background: #111; border: 1px solid #222; padding: 12px 14px; border-radius: 0; }
    .metric-card .label { font-size: 9px; font-weight: 700; color: #555; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px; }
    .metric-card .value { font-size: 20px; font-weight: 700; }
    .metric-card .sub { font-size: 11px; margin-top: 2px; }
    .topbar { background: #1a1a1a; border-bottom: 1px solid #cc7000; padding: 6px 0; margin-bottom: 8px; }
    .topbar-title { font-size: 14px; font-weight: 700; color: #ff8c00; letter-spacing: 0.1em; }
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════
# PERSISTENT STORAGE — survives page refresh
# ════════════════════════════════════════════════════
import os
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'portfolio_data.json')

def save_to_disk():
    """Save current state to JSON file"""
    try:
        export = {
            'positions': st.session_state.positions.to_dict('records') if isinstance(st.session_state.positions, pd.DataFrame) and len(st.session_state.positions) > 0 else [],
            'rebalances': st.session_state.rebalances.to_dict('records') if isinstance(st.session_state.rebalances, pd.DataFrame) and len(st.session_state.rebalances) > 0 else [],
            'benchmark': st.session_state.benchmark_components,
            'inception': st.session_state.inception_date,
            'account_data': st.session_state.get('account_data', {}),
        }
        with open(DATA_FILE, 'w') as f:
            json.dump(export, f, default=str)
    except Exception as e:
        pass  # Silent fail on write errors

def load_from_disk():
    """Load saved state from JSON file"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
            return data
    except:
        pass
    return None

# Initialize session state — try loading from disk first
saved = load_from_disk()
if 'positions' not in st.session_state:
    if saved and saved.get('positions'):
        st.session_state.positions = pd.DataFrame(saved['positions'])
    else:
        st.session_state.positions = pd.DataFrame(columns=['ticker','name','sleeve','shares','avgCost'])
if 'rebalances' not in st.session_state:
    if saved and saved.get('rebalances'):
        st.session_state.rebalances = pd.DataFrame(saved['rebalances'])
    else:
        st.session_state.rebalances = pd.DataFrame(columns=['date','action','ticker','shares','price','notes'])
if 'benchmark_components' not in st.session_state:
    if saved and saved.get('benchmark'):
        st.session_state.benchmark_components = saved['benchmark']
    else:
        st.session_state.benchmark_components = [{'ticker': 'SPY', 'weight': 60}, {'ticker': 'ACWI', 'weight': 40}]
if 'inception_date' not in st.session_state:
    if saved and saved.get('inception'):
        st.session_state.inception_date = saved['inception']
    else:
        st.session_state.inception_date = '2026-02-02'
if 'account_data' not in st.session_state:
    if saved and saved.get('account_data'):
        st.session_state.account_data = saved['account_data']
    else:
        st.session_state.account_data = {'realized_pnl': 0, 'total_deposits': 0, 'total_dividends': 0}

KNOWN_ETFS = {'SPYM','RSPT','KBWB','PAVE','XBI','XTN','EUAD','AAXJ','SCHP','PPI','XAR',
              'UTES','EWJ','DXJ','EWY','IEMG','SPY','ACWI','QQQ','IWM','VTI','VOO','AGG'}

# ════════════════════════════════════════════════════
# SCHWAB CSV PARSER
# ════════════════════════════════════════════════════
def parse_schwab_csv(file):
    df = pd.read_csv(file, dtype=str)
    df.columns = df.columns.str.strip().str.replace('"', '')
    # Clean fields
    df['Date'] = df['Date'].str.split(' as of ').str[0]
    df['Quantity'] = pd.to_numeric(df['Quantity'].str.replace(r'[$,"]', '', regex=True), errors='coerce').fillna(0)
    df['Price'] = pd.to_numeric(df['Price'].str.replace(r'[$,"]', '', regex=True), errors='coerce').fillna(0)
    df['Amount'] = pd.to_numeric(df['Amount'].str.replace(r'[$,"]', '', regex=True), errors='coerce').fillna(0)
    df['Symbol'] = df['Symbol'].str.strip().str.replace('"', '')

    trades = df[df['Action'].isin(['Buy', 'Sell', 'Reinvest Shares', 'Cash In Lieu'])].copy()

    # CRITICAL: Sort chronologically — CSV is newest-first but we must process oldest-first
    trades['_parsed_date'] = pd.to_datetime(trades['Date'], format='%m/%d/%Y', errors='coerce')
    trades = trades.sort_values('_parsed_date', ascending=True).reset_index(drop=True)

    # Calculate positions using average cost method + track realized P&L
    positions = {}
    total_realized_pnl = 0.0

    for _, row in trades.iterrows():
        sym = row['Symbol']
        if not sym or pd.isna(sym):
            continue
        if sym not in positions:
            positions[sym] = {'shares': 0.0, 'cost': 0.0, 'desc': row.get('Description', sym), 'realized': 0.0}
        p = positions[sym]
        if row['Action'] in ['Buy', 'Reinvest Shares']:
            p['shares'] += row['Quantity']
            p['cost'] += row['Quantity'] * row['Price']
        elif row['Action'] == 'Sell':
            if p['shares'] > 0:
                avg = p['cost'] / p['shares']
                realized = (row['Price'] - avg) * row['Quantity']
                p['realized'] += realized
                total_realized_pnl += realized
                p['cost'] -= row['Quantity'] * avg
            p['shares'] -= row['Quantity']
        elif row['Action'] == 'Cash In Lieu':
            # Cash In Lieu = proceeds from fractional shares during stock split/corporate action
            # Treated as a partial sale: reduces cost basis proportionally
            cash_received = row['Amount']  # positive dollar amount
            if p['shares'] > 0 and p['cost'] > 0:
                # What fraction of the position was cashed out?
                # cash_received / (cash_received + remaining_value) approximation
                # Simpler: reduce cost basis by the cash received (cost recovery method)
                cost_reduction = min(cash_received, p['cost'])
                realized = cash_received - cost_reduction
                p['cost'] -= cost_reduction
                p['realized'] += realized
                total_realized_pnl += realized

    # Calculate total deposits (MoneyLink Transfers)
    transfers = df[df['Action'].str.contains('MoneyLink Transfer', na=False)]
    total_deposits = transfers['Amount'].sum()

    # Dividends: only actual cash dividends and reinvest dividends, NOT Cash In Lieu
    divs = df[df['Action'].str.contains('Cash Dividend|Reinvest Dividend', na=False, regex=True)]
    total_dividends = divs['Amount'].sum()

    rows = []
    for sym, p in positions.items():
        if p['shares'] > 0.0001:
            avg_cost = p['cost'] / p['shares'] if p['shares'] > 0 else 0
            sleeve = 'etf' if sym in KNOWN_ETFS else 'stock'
            rows.append({'ticker': sym, 'name': str(p['desc'])[:40], 'sleeve': sleeve,
                        'shares': round(p['shares'], 4), 'avgCost': round(avg_cost, 2)})

    # Build rebalance log
    rebal_rows = []
    for _, row in trades.iterrows():
        sym = row['Symbol']
        if not sym or pd.isna(sym):
            continue
        action = 'SELL' if row['Action'] == 'Sell' else ('ADD' if row['Action'] == 'Reinvest Shares' else 'BUY')
        rebal_rows.append({'date': row['Date'], 'action': action, 'ticker': sym,
                          'shares': row['Quantity'], 'price': row['Price'], 'notes': 'Schwab CSV'})

    # Account-level data
    account_data = {
        'realized_pnl': round(total_realized_pnl, 2),
        'total_deposits': round(total_deposits, 2),
        'total_dividends': round(total_dividends, 2),
    }

    return pd.DataFrame(rows), pd.DataFrame(rebal_rows), trades, account_data

# ════════════════════════════════════════════════════
# YFINANCE DATA
# ════════════════════════════════════════════════════
@st.cache_data(ttl=60)
def fetch_quotes(tickers):
    """Fetch current prices for all tickers"""
    if not tickers:
        return {}
    data = {}
    try:
        tickers_str = ' '.join(tickers)
        quotes = yf.Tickers(tickers_str)
        for t in tickers:
            try:
                info = quotes.tickers[t].fast_info
                price = info.get('lastPrice', 0) or info.get('last_price', 0)
                prev = info.get('previousClose', 0) or info.get('previous_close', 0)
                if price and price > 0:
                    data[t] = {
                        'price': price,
                        'prevClose': prev,
                        'change': price - prev if prev else 0,
                        'changePct': ((price - prev) / prev * 100) if prev else 0,
                    }
            except:
                pass
    except:
        pass
    return data

@st.cache_data(ttl=300)
def fetch_history(tickers, start_date, end_date=None):
    """Fetch historical daily closes for multiple tickers"""
    if not tickers:
        return pd.DataFrame()
    try:
        df = yf.download(tickers, start=start_date, end=end_date or now_eastern().strftime('%Y-%m-%d'),
                        auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            return df['Close']
        else:
            return df[['Close']].rename(columns={'Close': tickers[0]}) if len(tickers) == 1 else df
    except:
        return pd.DataFrame()

# ════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ════════════════════════════════════════════════════
def color_val(val, fmt_str='{:+.2f}%'):
    if pd.isna(val) or val == 0:
        return '<span style="color:#555">\u2014</span>'
    color = '#00d26a' if val >= 0 else '#ff3b3b'
    return f'<span style="color:{color};font-weight:700">{fmt_str.format(val)}</span>'

def color_dollar(val):
    if pd.isna(val) or val == 0:
        return '<span style="color:#555">\u2014</span>'
    color = '#00d26a' if val >= 0 else '#ff3b3b'
    sign = '+' if val >= 0 else '-'
    return f'<span style="color:{color};font-weight:700">{sign}${abs(val):,.2f}</span>'

def metric_card(label, value, delta=None, delta_color=None):
    delta_html = ''
    if delta is not None:
        dc = delta_color or ('#00d26a' if delta >= 0 else '#ff3b3b')
        delta_html = f'<div class="sub" style="color:{dc}">{delta:+.2f}%</div>'
    return f'<div class="metric-card"><div class="label">{label}</div><div class="value" style="color:{delta_color or "#e8e8e8"}">{value}</div>{delta_html}</div>'

# ════════════════════════════════════════════════════
# MAIN APP
# ════════════════════════════════════════════════════
now_et = now_eastern()
pos_df = st.session_state.positions
has_positions = len(pos_df) > 0 and pos_df['shares'].sum() > 0

# Fetch live prices
all_tickers = []
if has_positions:
    all_tickers = pos_df[pos_df['shares'] > 0]['ticker'].tolist()
bm_tickers = [c['ticker'] for c in st.session_state.benchmark_components]
all_tickers = list(set(all_tickers + bm_tickers))

quotes = fetch_quotes(all_tickers) if all_tickers else {}

# ─── Top Bar ────────────────────────────────────────
bm_label = ' / '.join([f"{c['weight']}% {c['ticker']}" for c in st.session_state.benchmark_components])

cols_top = st.columns([4, 1, 1, 1, 1])
with cols_top[0]:
    st.markdown(f'<div class="topbar-title">PORTFOLIO MONITOR</div>', unsafe_allow_html=True)
    st.caption(f"BM: {bm_label} | {len(pos_df[pos_df['shares']>0]) if has_positions else 0} positions | {now_et.strftime('%b %d, %I:%M %p')}")

# ─── Sidebar: Import & Config ──────────────────────
with st.sidebar:
    st.markdown("### IMPORT SCHWAB CSV")
    uploaded = st.file_uploader("Drop Schwab transaction CSV", type=['csv'], label_visibility='collapsed')
    if uploaded:
        # Only process if this is a new file (avoid infinite rerun loop)
        file_key = uploaded.name + str(uploaded.size)
        if st.session_state.get('_last_import') != file_key:
            pos_new, rebal_new, trades, acct_data = parse_schwab_csv(uploaded)
            if len(pos_new) > 0:
                st.session_state.positions = pos_new
                st.session_state.rebalances = rebal_new
                st.session_state.account_data = acct_data
                st.session_state._last_import = file_key
                save_to_disk()
                st.rerun()
        else:
            st.success(f"Imported {len(st.session_state.positions)} positions, {len(st.session_state.rebalances)} trades")

    st.markdown("---")
    st.markdown("### BENCHMARK")
    bm1_t = st.text_input("Ticker 1", value=st.session_state.benchmark_components[0]['ticker'])
    bm1_w = st.number_input("Weight 1", value=st.session_state.benchmark_components[0]['weight'], min_value=0)
    bm2_t = st.text_input("Ticker 2", value=st.session_state.benchmark_components[1]['ticker'] if len(st.session_state.benchmark_components) > 1 else '')
    bm2_w = st.number_input("Weight 2", value=st.session_state.benchmark_components[1]['weight'] if len(st.session_state.benchmark_components) > 1 else 0, min_value=0)
    if st.button("APPLY BENCHMARK"):
        comps = [{'ticker': bm1_t.upper(), 'weight': bm1_w}]
        if bm2_t:
            comps.append({'ticker': bm2_t.upper(), 'weight': bm2_w})
        st.session_state.benchmark_components = comps
        save_to_disk()
        st.rerun()

    st.markdown("---")
    st.markdown("### INCEPTION DATE")
    inc = st.date_input("Portfolio start", value=datetime.strptime(st.session_state.inception_date, '%Y-%m-%d'))
    st.session_state.inception_date = inc.strftime('%Y-%m-%d')
    save_to_disk()

    st.markdown("---")
    st.markdown("### DATA EXPORT")
    if st.button("EXPORT JSON"):
        export = {
            'positions': pos_df.to_dict('records') if has_positions else [],
            'rebalances': st.session_state.rebalances.to_dict('records') if len(st.session_state.rebalances) > 0 else [],
            'benchmark': st.session_state.benchmark_components,
            'inception': st.session_state.inception_date,
        }
        st.download_button("DOWNLOAD", json.dumps(export, indent=2, default=str), "portfolio.json", "application/json")

if not has_positions:
    st.markdown("## Welcome")
    st.markdown("Open the **sidebar** (arrow top-left) and **import your Schwab CSV** to get started.")
    st.stop()

# ════════════════════════════════════════════════════
# CALCULATIONS
# ════════════════════════════════════════════════════
active = pos_df[pos_df['shares'] > 0].copy()
active['price'] = active['ticker'].map(lambda t: quotes.get(t, {}).get('price', 0))
active['prevClose'] = active['ticker'].map(lambda t: quotes.get(t, {}).get('prevClose', 0))
active['mv'] = active['shares'] * active['price']
active['cost'] = active['shares'] * active['avgCost']
active['pnl'] = active['mv'] - active['cost']
active['totalRet'] = np.where(active['cost'] > 0, (active['pnl'] / active['cost']) * 100, 0)
active['dayChg'] = np.where(active['prevClose'] > 0, ((active['price'] - active['prevClose']) / active['prevClose']) * 100, 0)
active['dayPnl'] = active['shares'] * (active['price'] - active['prevClose'])

total_mv = active['mv'].sum()
total_cost = active['cost'].sum()
unrealized_pnl = total_mv - total_cost
unrealized_ret = (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0
total_daily_pnl = active['dayPnl'].sum()
daily_ret = (total_daily_pnl / (total_mv - total_daily_pnl) * 100) if (total_mv - total_daily_pnl) > 0 else 0

# Realized P&L from closed positions
acct = st.session_state.account_data
realized_pnl = acct.get('realized_pnl', 0)
total_deposits = acct.get('total_deposits', 0)
total_dividends = acct.get('total_dividends', 0)

# Total P&L = Realized + Unrealized (true portfolio performance)
total_pnl = realized_pnl + unrealized_pnl
# Total return based on deposits (money-weighted)
total_ret = (total_pnl / total_deposits * 100) if total_deposits > 0 else 0

active['weight'] = np.where(total_mv > 0, (active['mv'] / total_mv) * 100, 0)
active['attrib'] = active['weight'] * active['dayChg'] / 100  # Attribution (contribution to return)

# ── CTR: Contribution to Risk ──────────────────────
# CTR_i = w_i × MCTR_i, where MCTR_i = β_i × σ_P
# PCR_i = CTR_i / σ_P = w_i × β_i (percent contribution to risk)
# Uses 30-day daily returns
active['beta'] = 0.0
active['mctr'] = 0.0
active['ctr_risk'] = 0.0
active['pcr'] = 0.0
port_vol = 0.0

try:
    ctr_tickers = active['ticker'].tolist()
    if len(ctr_tickers) >= 2:
        ctr_start = (now_et - timedelta(days=45)).strftime('%Y-%m-%d')
        ctr_hist = fetch_history(ctr_tickers, ctr_start)
        if not ctr_hist.empty and len(ctr_hist) >= 10:
            # Daily returns
            ctr_returns = ctr_hist.pct_change().dropna()
            # Portfolio weights as array (decimal, not percent)
            weights = active.set_index('ticker')['weight'].reindex(ctr_returns.columns).fillna(0).values / 100
            # Portfolio daily return series
            port_returns = (ctr_returns * weights).sum(axis=1)
            # Portfolio volatility (annualized)
            port_vol = port_returns.std() * np.sqrt(252)
            # Per-asset beta to portfolio
            for idx, row in active.iterrows():
                t = row['ticker']
                if t in ctr_returns.columns:
                    cov_ip = ctr_returns[t].cov(port_returns)
                    var_p = port_returns.var()
                    beta_i = cov_ip / var_p if var_p > 0 else 0
                    w_i = row['weight'] / 100
                    mctr_i = beta_i * port_vol
                    ctr_i = w_i * mctr_i
                    pcr_i = (ctr_i / port_vol * 100) if port_vol > 0 else 0
                    active.at[idx, 'beta'] = round(beta_i, 3)
                    active.at[idx, 'mctr'] = round(mctr_i * 100, 3)  # as percent
                    active.at[idx, 'ctr_risk'] = round(ctr_i * 100, 3)  # as percent
                    active.at[idx, 'pcr'] = round(pcr_i, 1)  # percent contribution to risk
except Exception as e:
    pass  # Silently fall back to zeros if history unavailable

# Blended benchmark
bm_comps = st.session_state.benchmark_components
total_bm_weight = sum(c['weight'] for c in bm_comps)
blended_chg = sum((c['weight'] / total_bm_weight) * quotes.get(c['ticker'], {}).get('changePct', 0) for c in bm_comps) if total_bm_weight > 0 else 0

# ── Jensen's Alpha & Cumulative Over/Underperformance ──
# Uses inception-to-date returns
jensens_alpha = None
port_beta_to_bm = None
cum_port_ret = None
cum_bm_ret = None
cum_excess = None
rf_rate = 0.043  # ~4.3% annualized risk-free (T-bill proxy)

try:
    inception = st.session_state.inception_date
    bm_tickers_for_alpha = [c['ticker'] for c in bm_comps]
    all_alpha_tickers = list(set(active['ticker'].tolist() + bm_tickers_for_alpha))
    alpha_hist = fetch_history(all_alpha_tickers, inception)

    if not alpha_hist.empty and len(alpha_hist) >= 5:
        # Daily returns
        alpha_returns = alpha_hist.pct_change().dropna()

        # Portfolio daily return series (weighted by current holdings)
        port_daily = pd.Series(0.0, index=alpha_returns.index)
        for _, row in active.iterrows():
            t = row['ticker']
            w = row['weight'] / 100
            if t in alpha_returns.columns:
                port_daily += w * alpha_returns[t]

        # Blended benchmark daily return series
        bm_daily = pd.Series(0.0, index=alpha_returns.index)
        for c in bm_comps:
            t = c['ticker']
            w = c['weight'] / total_bm_weight if total_bm_weight > 0 else 0
            if t in alpha_returns.columns:
                bm_daily += w * alpha_returns[t]

        # Cumulative returns
        cum_port_ret = ((1 + port_daily).cumprod().iloc[-1] - 1) * 100
        cum_bm_ret = ((1 + bm_daily).cumprod().iloc[-1] - 1) * 100
        cum_excess = cum_port_ret - cum_bm_ret

        # Annualize
        n_days = len(alpha_returns)
        ann_factor = 252 / n_days if n_days > 0 else 1
        ann_port = ((1 + cum_port_ret / 100) ** ann_factor - 1) * 100
        ann_bm = ((1 + cum_bm_ret / 100) ** ann_factor - 1) * 100

        # Portfolio beta to benchmark
        cov_pb = port_daily.cov(bm_daily)
        var_bm = bm_daily.var()
        port_beta_to_bm = cov_pb / var_bm if var_bm > 0 else 1.0

        # Jensen's Alpha (annualized) = Rp - [Rf + β(Rm - Rf)]
        rf_daily = rf_rate / 252
        jensens_alpha = ann_port - (rf_rate * 100 + port_beta_to_bm * (ann_bm - rf_rate * 100))

except Exception as e:
    pass

# Sleeves
etf = active[active['sleeve'] == 'etf']
stock = active[active['sleeve'] == 'stock']
etf_mv = etf['mv'].sum()
stock_mv = stock['mv'].sum()
etf_w = (etf_mv / total_mv * 100) if total_mv > 0 else 0
stock_w = (stock_mv / total_mv * 100) if total_mv > 0 else 0
etf_daily = (etf['dayPnl'].sum() / (etf_mv - etf['dayPnl'].sum()) * 100) if (etf_mv - etf['dayPnl'].sum()) > 0 else 0
stock_daily = (stock['dayPnl'].sum() / (stock_mv - stock['dayPnl'].sum()) * 100) if (stock_mv - stock['dayPnl'].sum()) > 0 else 0
etf_ret = ((etf_mv - etf['cost'].sum()) / etf['cost'].sum() * 100) if etf['cost'].sum() > 0 else 0
stock_ret = ((stock_mv - stock['cost'].sum()) / stock['cost'].sum() * 100) if stock['cost'].sum() > 0 else 0

# ════════════════════════════════════════════════════
# SUMMARY STRIP
# ════════════════════════════════════════════════════
# Row 1: Portfolio-level P&L
r1c1, r1c2, r1c3, r1c4, r1c5 = st.columns(5)
with r1c1:
    st.metric("NET EQUITY", f"${total_mv:,.2f}", f"Cost: ${total_cost:,.2f}")
with r1c2:
    st.metric("DAY P&L", f"{'+'if total_daily_pnl>=0 else ''}{total_daily_pnl:,.2f}", f"{daily_ret:+.2f}% today",
              delta_color="normal" if total_daily_pnl >= 0 else "inverse")
with r1c3:
    st.metric("UNREALIZED P&L", f"{'+'if unrealized_pnl>=0 else ''}{unrealized_pnl:,.2f}", f"{unrealized_ret:+.2f}% vs cost",
              delta_color="normal" if unrealized_pnl >= 0 else "inverse")
with r1c4:
    st.metric("REALIZED P&L", f"{'+'if realized_pnl>=0 else ''}{realized_pnl:,.2f}", f"Divs: ${total_dividends:,.2f}",
              delta_color="normal" if realized_pnl >= 0 else "inverse")
with r1c5:
    st.metric("TOTAL P&L", f"{'+'if total_pnl>=0 else ''}{total_pnl:,.2f}", f"{total_ret:+.2f}% on ${total_deposits:,.0f} deposited",
              delta_color="normal" if total_pnl >= 0 else "inverse")

# Row 2: Benchmark, Alpha, Sleeves, Vol
r2c1, r2c2, r2c3, r2c4, r2c5 = st.columns(5)
with r2c1:
    bm_parts = ' / '.join([f"{c['ticker']} {quotes.get(c['ticker'],{}).get('changePct',0):+.2f}%" for c in bm_comps])
    st.metric("BM DAY CHG", f"{blended_chg:+.2f}%", bm_parts)
with r2c2:
    # Excess return = portfolio daily return - benchmark daily return (NOT Jensen's alpha)
    excess = daily_ret - blended_chg
    st.metric("EXCESS RTN (DAY)", f"{excess:+.2f}%", "Port day - BM day",
              delta_color="normal" if excess >= 0 else "inverse")
with r2c3:
    st.metric("ETF SLEEVE (DAY)", f"{etf_daily:+.2f}%", f"{etf_w:.1f}% of port \u00b7 {len(etf)} pos \u00b7 {etf_ret:+.1f}% total")
with r2c4:
    st.metric("STOCK SLEEVE (DAY)", f"{stock_daily:+.2f}%", f"{stock_w:.1f}% of port \u00b7 {len(stock)} pos \u00b7 {stock_ret:+.1f}% total")
with r2c5:
    st.metric("PORT VOL (ANN)", f"{port_vol*100:.1f}%" if port_vol > 0 else "\u2014", "30d daily returns \u00d7 \u221a252" if port_vol > 0 else "Need 10+ days data")

# Row 3: Alpha, Cumulative Performance vs Benchmark
r3c1, r3c2, r3c3, r3c4, r3c5 = st.columns(5)
with r3c1:
    if jensens_alpha is not None:
        st.metric("JENSEN'S \u03b1 (ANN)", f"{jensens_alpha:+.2f}%",
                  f"Rp\u2212[Rf+\u03b2(Rm\u2212Rf)]",
                  delta_color="normal" if jensens_alpha >= 0 else "inverse")
    else:
        st.metric("JENSEN'S \u03b1 (ANN)", "\u2014", "Need 5+ days history")
with r3c2:
    if port_beta_to_bm is not None:
        st.metric("PORT \u03b2 TO BM", f"{port_beta_to_bm:.2f}", f"Cov(Rp,Rm)/Var(Rm) since inception")
    else:
        st.metric("PORT \u03b2 TO BM", "\u2014", "Need 5+ days history")
with r3c3:
    if cum_port_ret is not None:
        st.metric("PORT RTN (INCEP)", f"{cum_port_ret:+.2f}%", f"Since {st.session_state.inception_date}",
                  delta_color="normal" if cum_port_ret >= 0 else "inverse")
    else:
        st.metric("PORT RTN (INCEP)", "\u2014")
with r3c4:
    if cum_bm_ret is not None:
        bm_label_short = '/'.join([c['ticker'] for c in bm_comps])
        st.metric(f"BM RTN (INCEP)", f"{cum_bm_ret:+.2f}%", f"{bm_label_short} since inception",
                  delta_color="normal" if cum_bm_ret >= 0 else "inverse")
    else:
        st.metric("BM RTN (INCEP)", "\u2014")
with r3c5:
    if cum_excess is not None:
        label = "OUTPERFORMANCE" if cum_excess >= 0 else "UNDERPERFORMANCE"
        st.metric(label, f"{cum_excess:+.2f}%", f"Port \u2212 BM cumulative",
                  delta_color="normal" if cum_excess >= 0 else "inverse")
    else:
        st.metric("VS BENCHMARK", "\u2014")

# ════════════════════════════════════════════════════
# PERFORMANCE CHART
# ════════════════════════════════════════════════════
st.markdown("#### PORTFOLIO VS BLENDED BENCHMARK")

period_cols = st.columns([1, 1, 1, 1, 6])
periods = {'INCEP': st.session_state.inception_date, 'YTD': f'{now_et.year}-01-01',
           '1M': (now_et - timedelta(days=30)).strftime('%Y-%m-%d'),
           '7D': (now_et - timedelta(days=7)).strftime('%Y-%m-%d')}

period_choice = 'INCEP'
for i, (label, start) in enumerate(periods.items()):
    with period_cols[i]:
        if st.button(label, key=f'period_{label}', use_container_width=True):
            period_choice = label

# Use session state for period persistence
if 'chart_period' not in st.session_state:
    st.session_state.chart_period = 'INCEP'
for label in periods:
    if st.session_state.get(f'period_{label}_clicked'):
        st.session_state.chart_period = label
# Check which button was just clicked
for label in periods:
    if f'period_{label}' in st.session_state and st.session_state[f'period_{label}']:
        st.session_state.chart_period = label

start_date = periods[st.session_state.chart_period]

# Fetch history
hist_tickers = active['ticker'].tolist() + bm_tickers
hist_tickers = list(set(hist_tickers))
hist = fetch_history(hist_tickers, start_date)

if not hist.empty and len(hist) >= 2:
    # Portfolio value per day
    port_val = pd.Series(0.0, index=hist.index)
    for _, row in active.iterrows():
        t = row['ticker']
        if t in hist.columns:
            port_val += row['shares'] * hist[t].fillna(method='ffill').fillna(row['avgCost'])
        else:
            port_val += row['shares'] * row['avgCost']

    # Blended benchmark
    bm_val = pd.Series(0.0, index=hist.index)
    for c in bm_comps:
        t = c['ticker']
        w = c['weight'] / total_bm_weight if total_bm_weight > 0 else 0
        if t in hist.columns:
            bm_val += w * hist[t].fillna(method='ffill')

    # Cumulative returns
    port_ret = ((port_val / port_val.iloc[0]) - 1) * 100
    bm_ret = ((bm_val / bm_val.iloc[0]) - 1) * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=port_ret.index, y=port_ret.values, name='Portfolio',
                            line=dict(color='#ff8c00', width=2), fill='tozeroy',
                            fillcolor='rgba(255,140,0,0.04)'))
    fig.add_trace(go.Scatter(x=bm_ret.index, y=bm_ret.values, name=bm_label,
                            line=dict(color='#555', width=1.5, dash='dash')))
    fig.update_layout(
        template='plotly_dark', paper_bgcolor='#111', plot_bgcolor='#111',
        margin=dict(l=50, r=20, t=30, b=40), height=320,
        xaxis=dict(gridcolor='#222', showgrid=True), yaxis=dict(gridcolor='#222', showgrid=True, tickformat='+.1f', ticksuffix='%'),
        legend=dict(orientation='h', yanchor='top', y=1.02, xanchor='right', x=1, font=dict(size=10)),
        hovermode='x unified',
    )
    st.plotly_chart(fig, use_container_width=True)

    pc = st.columns(2)
    with pc[0]:
        st.caption(f"Since {start_date} ({st.session_state.chart_period}) \u00b7 Port: {port_ret.iloc[-1]:+.2f}% vs BM: {bm_ret.iloc[-1]:+.2f}%")
else:
    st.info("Waiting for historical data...")

# ════════════════════════════════════════════════════
# ALLOCATION PIE CHARTS
# ════════════════════════════════════════════════════
pie_col1, pie_col2 = st.columns(2)

with pie_col1:
    st.markdown("#### POSITION ALLOCATION")
    if total_mv > 0:
        alloc = active[['ticker', 'weight']].sort_values('weight', ascending=False)
        fig_pie = go.Figure(data=[go.Pie(
            labels=alloc['ticker'], values=alloc['weight'],
            hole=0.5, textinfo='label+percent', textposition='auto',
            textfont=dict(size=10, color='white', family='Helvetica'),
            marker=dict(colors=px.colors.qualitative.Set2),
        )])
        fig_pie.update_layout(template='plotly_dark', paper_bgcolor='#111', plot_bgcolor='#111',
                             margin=dict(l=10, r=10, t=10, b=10), height=280, showlegend=False)
        st.plotly_chart(fig_pie, use_container_width=True)

with pie_col2:
    st.markdown("#### SLEEVE ALLOCATION")
    if total_mv > 0:
        sleeve_data = pd.DataFrame([
            {'Sleeve': 'ETF', 'Weight': etf_w},
            {'Sleeve': 'Stock', 'Weight': stock_w},
        ])
        fig_sleeve = go.Figure(data=[go.Pie(
            labels=sleeve_data['Sleeve'], values=sleeve_data['Weight'],
            hole=0.5, textinfo='label+percent', textposition='auto',
            textfont=dict(size=12, color='white', family='Helvetica'),
            marker=dict(colors=['#00bfff', '#ffd700']),
        )])
        fig_sleeve.update_layout(template='plotly_dark', paper_bgcolor='#111', plot_bgcolor='#111',
                                margin=dict(l=10, r=10, t=10, b=10), height=280, showlegend=False)
        st.plotly_chart(fig_sleeve, use_container_width=True)

# ════════════════════════════════════════════════════
# HOLDINGS TABLE
# ════════════════════════════════════════════════════
st.markdown("#### HOLDINGS")

tab_all, tab_etf, tab_stock = st.tabs(["ALL", "ETF", "STOCK"])

def show_holdings(df):
    if len(df) == 0:
        st.info("No positions")
        return
    display = df[['ticker', 'sleeve', 'shares', 'avgCost', 'price', 'mv', 'weight', 'dayChg', 'dayPnl', 'totalRet', 'pnl', 'attrib', 'beta', 'ctr_risk', 'pcr']].copy()
    display.columns = ['Ticker', 'Sleeve', 'Shares', 'Avg Cost', 'Price', 'Mkt Value', 'Weight %', 'Day Chg %', 'Day P&L', 'Total Rtn %', 'Total P&L', 'Attrib %', 'Beta', 'CTR %', 'PCR %']
    display = display.sort_values('Mkt Value', ascending=False)

    st.dataframe(
        display.style.format({
            'Shares': '{:.4f}', 'Avg Cost': '${:.2f}', 'Price': '${:.2f}',
            'Mkt Value': '${:,.2f}', 'Weight %': '{:.1f}%', 'Day Chg %': '{:+.2f}%',
            'Day P&L': '${:+,.2f}', 'Total Rtn %': '{:+.2f}%', 'Total P&L': '${:+,.2f}',
            'Attrib %': '{:+.3f}%', 'Beta': '{:.2f}', 'CTR %': '{:+.3f}%', 'PCR %': '{:.1f}%',
        }).applymap(lambda v: 'color: #00d26a' if isinstance(v, (int, float)) and v > 0 else ('color: #ff3b3b' if isinstance(v, (int, float)) and v < 0 else ''),
                   subset=['Day Chg %', 'Day P&L', 'Total Rtn %', 'Total P&L', 'Attrib %']),
        use_container_width=True, height=min(400, 40 + len(display) * 35)
    )

with tab_all:
    show_holdings(active)
with tab_etf:
    show_holdings(etf)
with tab_stock:
    show_holdings(stock)

# ════════════════════════════════════════════════════
# SLEEVE BREAKDOWN
# ════════════════════════════════════════════════════
sl1, sl2 = st.columns(2)

with sl1:
    st.markdown("#### ETF SLEEVE")
    e1, e2, e3 = st.columns(3)
    with e1: st.metric("MKT VALUE", f"${etf_mv:,.2f}")
    with e2: st.metric("WEIGHT", f"{etf_w:.1f}%")
    with e3: st.metric("TOTAL RTN", f"{etf_ret:+.2f}%", delta_color="normal" if etf_ret >= 0 else "inverse")

with sl2:
    st.markdown("#### STOCK SLEEVE")
    s1, s2, s3 = st.columns(3)
    with s1: st.metric("MKT VALUE", f"${stock_mv:,.2f}")
    with s2: st.metric("WEIGHT", f"{stock_w:.1f}%")
    with s3: st.metric("TOTAL RTN", f"{stock_ret:+.2f}%", delta_color="normal" if stock_ret >= 0 else "inverse")

# ════════════════════════════════════════════════════
# LIVE PRICES PANEL
# ════════════════════════════════════════════════════
with st.expander("LIVE PRICES", expanded=False):
    price_rows = []
    for c in bm_comps:
        q = quotes.get(c['ticker'], {})
        price_rows.append({'Ticker': c['ticker'], 'Type': f"BM {c['weight']}%",
                          'Price': q.get('price', 0), 'Chg %': q.get('changePct', 0)})
    # Blended
    price_rows.append({'Ticker': 'BLEND', 'Type': bm_label, 'Price': 0, 'Chg %': blended_chg})
    for _, row in active.iterrows():
        q = quotes.get(row['ticker'], {})
        price_rows.append({'Ticker': row['ticker'], 'Type': row['sleeve'].upper(),
                          'Price': q.get('price', 0), 'Chg %': q.get('changePct', 0)})
    pdf = pd.DataFrame(price_rows)
    st.dataframe(pdf.style.format({'Price': '${:.2f}', 'Chg %': '{:+.2f}%'}).applymap(
        lambda v: 'color: #00d26a' if isinstance(v, (int, float)) and v > 0 else ('color: #ff3b3b' if isinstance(v, (int, float)) and v < 0 else ''),
        subset=['Chg %']), use_container_width=True)

# ════════════════════════════════════════════════════
# REBALANCE LOG
# ════════════════════════════════════════════════════
st.markdown("#### REBALANCE LOG")

with st.expander("ADD ENTRY", expanded=False):
    rc = st.columns([2, 1, 1, 1, 1, 3])
    with rc[0]: rb_date = st.date_input("Date", value=now_et, key='rb_date')
    with rc[1]: rb_action = st.selectbox("Action", ['BUY', 'SELL', 'TRIM', 'ADD', 'ROTATE'], key='rb_action')
    with rc[2]: rb_ticker = st.text_input("Ticker", key='rb_ticker')
    with rc[3]: rb_shares = st.number_input("Shares", value=0.0, step=0.01, key='rb_shares')
    with rc[4]: rb_price = st.number_input("Price", value=0.0, step=0.01, key='rb_price')
    with rc[5]: rb_notes = st.text_input("Notes", key='rb_notes')
    if st.button("LOG REBALANCE"):
        ticker_up = rb_ticker.upper().strip()
        if not ticker_up or rb_shares <= 0 or rb_price <= 0:
            st.error("Enter valid ticker, shares, and price")
        else:
            # 1. Log to rebalance journal
            new_row = pd.DataFrame([{
                'date': rb_date.strftime('%m/%d/%Y'), 'action': rb_action,
                'ticker': ticker_up, 'shares': rb_shares, 'price': rb_price, 'notes': rb_notes
            }])
            st.session_state.rebalances = pd.concat([new_row, st.session_state.rebalances], ignore_index=True)

            # 2. Update positions
            pos = st.session_state.positions
            existing = pos[pos['ticker'] == ticker_up]
            sleeve = 'etf' if ticker_up in KNOWN_ETFS else 'stock'

            if rb_action in ['BUY', 'ADD']:
                if len(existing) > 0:
                    idx = existing.index[0]
                    old_shares = pos.at[idx, 'shares']
                    old_cost = old_shares * pos.at[idx, 'avgCost']
                    new_shares = old_shares + rb_shares
                    new_cost = old_cost + (rb_shares * rb_price)
                    pos.at[idx, 'shares'] = round(new_shares, 4)
                    pos.at[idx, 'avgCost'] = round(new_cost / new_shares, 2) if new_shares > 0 else 0
                else:
                    new_pos = pd.DataFrame([{'ticker': ticker_up, 'name': ticker_up, 'sleeve': sleeve,
                                            'shares': round(rb_shares, 4), 'avgCost': round(rb_price, 2)}])
                    st.session_state.positions = pd.concat([pos, new_pos], ignore_index=True)

            elif rb_action in ['SELL', 'TRIM']:
                if len(existing) > 0:
                    idx = existing.index[0]
                    old_shares = pos.at[idx, 'shares']
                    old_avg = pos.at[idx, 'avgCost']
                    sell_qty = min(rb_shares, old_shares)  # Can't sell more than you own

                    # Track realized P&L
                    realized_from_sell = (rb_price - old_avg) * sell_qty
                    acct = st.session_state.account_data
                    acct['realized_pnl'] = acct.get('realized_pnl', 0) + round(realized_from_sell, 2)
                    st.session_state.account_data = acct

                    # Reduce shares (avg cost stays the same)
                    new_shares = old_shares - sell_qty
                    if new_shares < 0.0001:
                        st.session_state.positions = pos.drop(idx).reset_index(drop=True)
                    else:
                        pos.at[idx, 'shares'] = round(new_shares, 4)
                else:
                    st.warning(f"No position in {ticker_up} to sell")

            elif rb_action == 'ROTATE':
                # ROTATE = sell old + buy new. Notes should specify "FROM:XTN TO:PPI" etc.
                # Just log it — user handles the buy/sell separately
                pass

            save_to_disk()
            st.rerun()

if len(st.session_state.rebalances) > 0:
    rebal = st.session_state.rebalances.copy()
    rebal['notional'] = rebal['shares'] * rebal['price']
    st.dataframe(
        rebal[['date', 'action', 'ticker', 'shares', 'price', 'notional', 'notes']].style.format({
            'shares': '{:.4f}', 'price': '${:.2f}', 'notional': '${:,.2f}'
        }).applymap(lambda v: 'color: #00d26a' if v in ['BUY', 'ADD'] else ('color: #ff3b3b' if v in ['SELL', 'TRIM'] else ''),
                   subset=['action']),
        use_container_width=True, height=min(300, 40 + len(rebal) * 35)
    )
else:
    st.info("No rebalances logged")

# ─── Auto-refresh ───────────────────────────────────
st.markdown("---")
st.caption(f"Last updated: {now_et.strftime('%I:%M:%S %p ET')} \u00b7 Refresh page to update prices")
