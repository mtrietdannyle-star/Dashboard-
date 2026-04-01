"""
Stock Factor Screener & Scoring Model
======================================
Designed for integration into a Streamlit portfolio dashboard.
Implements a two-stage process:
  1. Quality Gate (binary pass/fail) — eliminates low-quality names
  2. Multi-Factor Score (percentile rank) — ranks survivors

Data source: yfinance (Refinitiv/LSEG via Yahoo Finance)
Covers US large/mid/small caps with SEC-sourced fundamentals.

Usage:
  - Standalone: `streamlit run stock_screener.py`
  - As module: import scoring functions into existing dashboard

Author: Built for Danny's portfolio framework
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from datetime import datetime, timedelta
import warnings
import time

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
# CONFIGURATION & DEFAULTS
# ─────────────────────────────────────────────

DEFAULT_QUALITY_GATES = {
    "roic_min": 15.0,         # ROIC floor (%)
    "roe_min": 15.0,          # ROE floor (%)
    "net_debt_ebitda_max": 3.0,  # Leverage ceiling (x)
    "fcf_positive": True,     # Must generate positive FCF
    "gross_margin_min": 30.0, # Moat proxy (%)
}

DEFAULT_WEIGHTS = {
    "profitability": 0.25,
    "growth": 0.30,
    "financial_health": 0.20,
    "valuation": 0.15,
    "momentum": 0.10,
}

# Predefined watchlists for quick loading
WATCHLISTS = {
    "Cybersecurity": ["FTNT", "PANW", "CRWD", "ZS", "NET", "S", "TENB", "QLYS"],
    "Defense & Aerospace": ["BWXT", "LMT", "NOC", "GD", "RTX", "HII", "LHX", "AXON"],
    "Data Infra / SaaS": ["MSCI", "NOW", "CRM", "DDOG", "SNOW", "MDB", "CFLT", "ESTC"],
    "Semiconductor": ["NVDA", "AMD", "AVGO", "MRVL", "LRCX", "KLAC", "AMAT", "CDNS"],
    "Infrastructure / Industrials": ["PWR", "EME", "FIX", "URI", "MTZ", "GEV", "ETN", "AME"],
    "Custom": [],
}


# ─────────────────────────────────────────────
# DATA LAYER — Fetching & Calculations
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)  # Cache 1 hour
def fetch_stock_data(ticker: str) -> dict:
    """
    Pull fundamental data for a single ticker from yfinance.
    Returns a flat dict of raw metrics, calculating from
    financial statements where possible for accuracy.
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}

        # Pull financial statements (annual)
        try:
            inc = t.financials  # income statement
        except Exception:
            inc = pd.DataFrame()
        try:
            bs = t.balance_sheet
        except Exception:
            bs = pd.DataFrame()
        try:
            cf = t.cashflow
        except Exception:
            cf = pd.DataFrame()

        # --- Helper: safe extraction from statements ---
        def safe_get(df, field, col=0):
            """Safely get a value from a financial statement DataFrame."""
            if df is None or df.empty:
                return None
            for label in ([field] if isinstance(field, str) else field):
                if label in df.index:
                    try:
                        val = df.iloc[df.index.get_loc(label), col]
                        if pd.notna(val):
                            return float(val)
                    except (IndexError, KeyError):
                        continue
            return None

        # --- ROIC Calculation (from statements) ---
        # ROIC = NOPAT / Invested Capital
        # NOPAT = EBIT * (1 - effective_tax_rate)
        # Invested Capital = Total Equity + Total Debt - Cash
        ebit = safe_get(inc, ["EBIT", "Operating Income"])
        tax_provision = safe_get(inc, ["Tax Provision", "Income Tax Expense"])
        pretax_income = safe_get(inc, ["Pretax Income", "Income Before Tax"])

        total_equity = safe_get(bs, ["Stockholders Equity", "Total Stockholder Equity",
                                      "Common Stock Equity", "Stockholders' Equity"])
        total_debt = safe_get(bs, ["Total Debt", "Long Term Debt"])
        short_debt = safe_get(bs, ["Short Long Term Debt", "Current Debt",
                                    "Short Term Debt"]) or 0
        cash = safe_get(bs, ["Cash And Cash Equivalents", "Cash",
                              "Cash Cash Equivalents And Short Term Investments"]) or 0

        roic = None
        if ebit and pretax_income and pretax_income != 0 and total_equity:
            eff_tax = (tax_provision / pretax_income) if tax_provision else 0.21
            eff_tax = max(0, min(eff_tax, 0.5))  # Clamp to reasonable range
            nopat = ebit * (1 - eff_tax)
            debt_total = (total_debt or 0) + short_debt
            invested_capital = total_equity + debt_total - cash
            if invested_capital > 0:
                roic = (nopat / invested_capital) * 100

        # --- ROE (from statements, fallback to info) ---
        net_income = safe_get(inc, ["Net Income", "Net Income Common Stockholders"])
        roe = None
        if net_income and total_equity and total_equity > 0:
            roe = (net_income / total_equity) * 100
        elif info.get("returnOnEquity"):
            roe = info["returnOnEquity"] * 100

        # --- Margins ---
        total_revenue = safe_get(inc, ["Total Revenue", "Revenue"])
        gross_profit = safe_get(inc, ["Gross Profit"])
        operating_income = safe_get(inc, ["Operating Income", "EBIT"])

        gross_margin = None
        if gross_profit and total_revenue and total_revenue > 0:
            gross_margin = (gross_profit / total_revenue) * 100
        elif info.get("grossMargins"):
            gross_margin = info["grossMargins"] * 100

        operating_margin = None
        if operating_income and total_revenue and total_revenue > 0:
            operating_margin = (operating_income / total_revenue) * 100
        elif info.get("operatingMargins"):
            operating_margin = info["operatingMargins"] * 100

        net_margin = None
        if net_income and total_revenue and total_revenue > 0:
            net_margin = (net_income / total_revenue) * 100
        elif info.get("profitMargins"):
            net_margin = info["profitMargins"] * 100

        # --- FCF & FCF Margin ---
        op_cashflow = safe_get(cf, ["Operating Cash Flow",
                                     "Total Cash From Operating Activities"])
        capex = safe_get(cf, ["Capital Expenditure", "Capital Expenditures"])
        # capex is typically negative in yfinance
        fcf = None
        if op_cashflow is not None and capex is not None:
            fcf = op_cashflow + capex  # capex is negative
        elif info.get("freeCashflow"):
            fcf = info["freeCashflow"]

        fcf_margin = None
        if fcf and total_revenue and total_revenue > 0:
            fcf_margin = (fcf / total_revenue) * 100

        # --- Leverage ---
        ebitda_val = safe_get(inc, ["EBITDA"])
        if ebitda_val is None:
            # Approximate: EBIT + D&A
            da = safe_get(cf, ["Depreciation And Amortization",
                                "Depreciation & Amortization"])
            if ebit and da:
                ebitda_val = ebit + abs(da)
            elif info.get("ebitda"):
                ebitda_val = info["ebitda"]

        debt_total_calc = (total_debt or 0) + short_debt
        net_debt = debt_total_calc - cash

        net_debt_ebitda = None
        if ebitda_val and ebitda_val > 0:
            net_debt_ebitda = net_debt / ebitda_val

        current_ratio = info.get("currentRatio")

        interest_expense = safe_get(inc, ["Interest Expense"])
        interest_coverage = None
        if ebit and interest_expense and interest_expense != 0:
            interest_coverage = abs(ebit / interest_expense)

        # --- Revenue Growth (YoY and 3Y CAGR) ---
        rev_growth_yoy = None
        rev_cagr_3y = None
        if inc is not None and not inc.empty and "Total Revenue" in inc.index:
            rev_series = inc.loc["Total Revenue"].dropna().sort_index()
            if len(rev_series) >= 2:
                rev_growth_yoy = ((rev_series.iloc[-1] / rev_series.iloc[-2]) - 1) * 100 \
                    if rev_series.iloc[-2] > 0 else None
            if len(rev_series) >= 4:
                # 3Y CAGR using oldest available up to 3 years back
                start_rev = rev_series.iloc[0]  # oldest
                end_rev = rev_series.iloc[-1]   # most recent
                n_years = (rev_series.index[-1] - rev_series.index[0]).days / 365.25
                if start_rev > 0 and n_years > 0:
                    rev_cagr_3y = ((end_rev / start_rev) ** (1 / n_years) - 1) * 100

        # Fallback to info
        if rev_growth_yoy is None and info.get("revenueGrowth"):
            rev_growth_yoy = info["revenueGrowth"] * 100

        # --- Earnings Growth ---
        earnings_growth = None
        if info.get("earningsGrowth"):
            earnings_growth = info["earningsGrowth"] * 100
        elif inc is not None and not inc.empty:
            ni_key = "Net Income" if "Net Income" in inc.index else \
                     "Net Income Common Stockholders" if "Net Income Common Stockholders" in inc.index else None
            if ni_key and len(inc.loc[ni_key].dropna()) >= 2:
                ni_series = inc.loc[ni_key].dropna().sort_index()
                if ni_series.iloc[-2] > 0:
                    earnings_growth = ((ni_series.iloc[-1] / ni_series.iloc[-2]) - 1) * 100

        # --- Valuation ---
        forward_pe = info.get("forwardPE")
        trailing_pe = info.get("trailingPE")
        peg = info.get("pegRatio")
        ev_ebitda = info.get("enterpriseToEbitda")
        ev_revenue = info.get("enterpriseToRevenue")
        price_to_book = info.get("priceToBook")

        # --- Price & Momentum ---
        market_cap = info.get("marketCap")
        price = info.get("currentPrice") or info.get("regularMarketPrice")

        # 3-month and 6-month returns
        try:
            hist = t.history(period="6mo")
            if not hist.empty and len(hist) > 1:
                current_price = hist["Close"].iloc[-1]
                # 3M return
                target_3m = datetime.now() - timedelta(days=63)
                idx_3m = hist.index.get_indexer([target_3m], method="nearest")[0]
                if idx_3m >= 0:
                    price_3m = hist["Close"].iloc[idx_3m]
                    return_3m = ((current_price / price_3m) - 1) * 100
                else:
                    return_3m = None
                # 6M return
                price_6m = hist["Close"].iloc[0]
                return_6m = ((current_price / price_6m) - 1) * 100
            else:
                return_3m = None
                return_6m = None
        except Exception:
            return_3m = None
            return_6m = None

        # --- Analyst Consensus ---
        target_price = info.get("targetMeanPrice")
        recommendation = info.get("recommendationKey")
        num_analysts = info.get("numberOfAnalystOpinions")
        upside = None
        if target_price and price and price > 0:
            upside = ((target_price / price) - 1) * 100

        # --- Company Info ---
        sector = info.get("sector", "N/A")
        industry = info.get("industry", "N/A")
        name = info.get("shortName") or info.get("longName") or ticker

        return {
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "industry": industry,
            "market_cap": market_cap,
            "price": price,
            # Profitability
            "roic": roic,
            "roe": roe,
            "gross_margin": gross_margin,
            "operating_margin": operating_margin,
            "net_margin": net_margin,
            "fcf_margin": fcf_margin,
            # Growth
            "rev_growth_yoy": rev_growth_yoy,
            "rev_cagr_3y": rev_cagr_3y,
            "earnings_growth": earnings_growth,
            # Financial Health
            "net_debt_ebitda": net_debt_ebitda,
            "current_ratio": current_ratio,
            "interest_coverage": interest_coverage,
            "fcf": fcf,
            # Valuation
            "forward_pe": forward_pe,
            "trailing_pe": trailing_pe,
            "peg": peg,
            "ev_ebitda": ev_ebitda,
            "ev_revenue": ev_revenue,
            "price_to_book": price_to_book,
            # Momentum
            "return_3m": return_3m,
            "return_6m": return_6m,
            # Analyst
            "analyst_target_upside": upside,
            "recommendation": recommendation,
            "num_analysts": num_analysts,
            # Meta
            "data_quality": "full",
        }

    except Exception as e:
        return {
            "ticker": ticker,
            "name": ticker,
            "sector": "ERROR",
            "data_quality": f"error: {str(e)[:80]}",
        }


def fetch_batch(tickers: list, progress_callback=None) -> pd.DataFrame:
    """Fetch data for multiple tickers, returning a DataFrame."""
    results = []
    for i, ticker in enumerate(tickers):
        data = fetch_stock_data(ticker.strip().upper())
        results.append(data)
        if progress_callback:
            progress_callback((i + 1) / len(tickers))
        time.sleep(0.2)  # Rate limiting — be polite to Yahoo
    df = pd.DataFrame(results)
    df = df.set_index("ticker")
    return df


# ─────────────────────────────────────────────
# QUALITY GATE — Binary Pass/Fail
# ─────────────────────────────────────────────

def apply_quality_gate(df: pd.DataFrame, gates: dict) -> pd.DataFrame:
    """
    Apply binary quality filters. Adds a 'gate_pass' column
    and individual gate columns showing which tests passed.
    """
    df = df.copy()

    # Individual gate checks
    df["gate_roic"] = df["roic"].apply(
        lambda x: x >= gates["roic_min"] if pd.notna(x) else False)
    df["gate_roe"] = df["roe"].apply(
        lambda x: x >= gates["roe_min"] if pd.notna(x) else False)
    df["gate_leverage"] = df["net_debt_ebitda"].apply(
        lambda x: x <= gates["net_debt_ebitda_max"] if pd.notna(x) else True)
        # True if missing — net cash companies often show as None
    df["gate_fcf"] = df["fcf"].apply(
        lambda x: x > 0 if pd.notna(x) else False) if gates["fcf_positive"] else True
    df["gate_gross_margin"] = df["gross_margin"].apply(
        lambda x: x >= gates["gross_margin_min"] if pd.notna(x) else False)

    # Composite gate
    gate_cols = [c for c in df.columns if c.startswith("gate_")]
    df["gate_pass"] = df[gate_cols].all(axis=1)
    df["gates_passed"] = df[gate_cols].sum(axis=1)
    df["gates_total"] = len(gate_cols)

    return df


# ─────────────────────────────────────────────
# SCORING ENGINE — Percentile-Based Ranking
# ─────────────────────────────────────────────

def percentile_rank(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """
    Convert a series of raw values into 0-100 percentile scores.
    Handles NaN by assigning 50 (neutral) — conservative choice
    that neither penalizes nor rewards missing data.
    """
    ranked = series.rank(pct=True, na_option="keep")
    if not higher_is_better:
        ranked = 1 - ranked
    # Scale to 0-100
    scored = ranked * 100
    # Fill NaN with 50 (neutral)
    scored = scored.fillna(50)
    return scored


def score_profitability(df: pd.DataFrame) -> pd.Series:
    """
    Profitability composite: ROIC, ROE, Operating Margin, FCF Margin
    Equal-weighted within dimension.
    """
    components = pd.DataFrame(index=df.index)
    components["roic_score"] = percentile_rank(df["roic"])
    components["roe_score"] = percentile_rank(df["roe"])
    components["op_margin_score"] = percentile_rank(df["operating_margin"])
    components["fcf_margin_score"] = percentile_rank(df["fcf_margin"])
    return components.mean(axis=1)


def score_growth(df: pd.DataFrame) -> pd.Series:
    """
    Growth composite: Revenue YoY, Revenue 3Y CAGR, Earnings Growth
    Weighted toward forward-looking where available.
    """
    components = pd.DataFrame(index=df.index)
    components["rev_yoy"] = percentile_rank(df["rev_growth_yoy"])
    components["rev_cagr"] = percentile_rank(df["rev_cagr_3y"])
    components["earn_growth"] = percentile_rank(df["earnings_growth"])
    # Weight: 40% YoY, 35% CAGR, 25% earnings growth
    return (components["rev_yoy"] * 0.40 +
            components["rev_cagr"] * 0.35 +
            components["earn_growth"] * 0.25)


def score_financial_health(df: pd.DataFrame) -> pd.Series:
    """
    Health composite: Net Debt/EBITDA (lower better), Current Ratio,
    Interest Coverage, FCF Margin
    """
    components = pd.DataFrame(index=df.index)
    components["leverage"] = percentile_rank(df["net_debt_ebitda"],
                                              higher_is_better=False)
    components["current"] = percentile_rank(df["current_ratio"])
    components["coverage"] = percentile_rank(df["interest_coverage"])
    components["fcf_margin"] = percentile_rank(df["fcf_margin"])
    return components.mean(axis=1)


def score_valuation(df: pd.DataFrame) -> pd.Series:
    """
    Valuation composite: Forward P/E, PEG, EV/EBITDA
    All lower = better (cheaper). PEG is the most useful single metric
    because it adjusts P/E for growth.
    """
    components = pd.DataFrame(index=df.index)
    # Filter out negative / extreme values before ranking
    fpe = df["forward_pe"].copy()
    fpe = fpe.where((fpe > 0) & (fpe < 200))
    components["fwd_pe"] = percentile_rank(fpe, higher_is_better=False)

    peg = df["peg"].copy()
    peg = peg.where((peg > 0) & (peg < 10))
    components["peg"] = percentile_rank(peg, higher_is_better=False)

    eve = df["ev_ebitda"].copy()
    eve = eve.where((eve > 0) & (eve < 100))
    components["ev_ebitda"] = percentile_rank(eve, higher_is_better=False)

    # Weight: PEG 40%, Forward PE 30%, EV/EBITDA 30%
    return (components["peg"] * 0.40 +
            components["fwd_pe"] * 0.30 +
            components["ev_ebitda"] * 0.30)


def score_momentum(df: pd.DataFrame) -> pd.Series:
    """
    Momentum composite: 3M return, 6M return, Analyst upside
    """
    components = pd.DataFrame(index=df.index)
    components["ret_3m"] = percentile_rank(df["return_3m"])
    components["ret_6m"] = percentile_rank(df["return_6m"])
    components["analyst_upside"] = percentile_rank(df["analyst_target_upside"])
    return (components["ret_3m"] * 0.40 +
            components["ret_6m"] * 0.30 +
            components["analyst_upside"] * 0.30)


def compute_composite_score(df: pd.DataFrame, weights: dict) -> pd.DataFrame:
    """
    Compute all dimension scores and weighted composite.
    Returns DataFrame with dimension scores + final composite.
    """
    scores = pd.DataFrame(index=df.index)
    scores["profitability"] = score_profitability(df)
    scores["growth"] = score_growth(df)
    scores["financial_health"] = score_financial_health(df)
    scores["valuation"] = score_valuation(df)
    scores["momentum"] = score_momentum(df)

    scores["composite"] = (
        scores["profitability"] * weights["profitability"] +
        scores["growth"] * weights["growth"] +
        scores["financial_health"] * weights["financial_health"] +
        scores["valuation"] * weights["valuation"] +
        scores["momentum"] * weights["momentum"]
    )

    scores["rank"] = scores["composite"].rank(ascending=False).astype(int)
    return scores


# ─────────────────────────────────────────────
# VISUALIZATION
# ─────────────────────────────────────────────

def radar_chart(scores_df: pd.DataFrame, tickers: list = None,
                title: str = "Factor Profile Comparison") -> go.Figure:
    """
    Radar chart comparing factor profiles of selected stocks.
    """
    dims = ["profitability", "growth", "financial_health", "valuation", "momentum"]
    labels = ["Profitability", "Growth", "Fin. Health", "Valuation", "Momentum"]

    if tickers is None:
        tickers = scores_df.index[:5].tolist()  # Top 5

    fig = go.Figure()
    colors = px.colors.qualitative.Set2

    for i, ticker in enumerate(tickers):
        if ticker in scores_df.index:
            vals = scores_df.loc[ticker, dims].tolist()
            vals.append(vals[0])  # Close the polygon
            fig.add_trace(go.Scatterpolar(
                r=vals,
                theta=labels + [labels[0]],
                fill="toself",
                name=ticker,
                opacity=0.6,
                line=dict(color=colors[i % len(colors)], width=2),
            ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], showticklabels=True,
                           tickfont=dict(size=10)),
            angularaxis=dict(tickfont=dict(size=12)),
        ),
        showlegend=True,
        title=dict(text=title, x=0.5, font=dict(size=16)),
        height=480,
        margin=dict(t=60, b=40, l=60, r=60),
    )
    return fig


def score_bar_chart(scores_df: pd.DataFrame, metric: str = "composite",
                    title: str = "Composite Score Ranking") -> go.Figure:
    """Horizontal bar chart of scores, sorted descending."""
    sorted_df = scores_df.sort_values(metric, ascending=True)

    colors = ["#2ecc71" if v >= 70 else "#f39c12" if v >= 50 else "#e74c3c"
              for v in sorted_df[metric]]

    fig = go.Figure(go.Bar(
        x=sorted_df[metric],
        y=sorted_df.index,
        orientation="h",
        marker_color=colors,
        text=sorted_df[metric].round(1),
        textposition="outside",
    ))

    fig.update_layout(
        title=dict(text=title, x=0.5, font=dict(size=16)),
        xaxis=dict(title="Score (0-100)", range=[0, 105]),
        yaxis=dict(title=""),
        height=max(300, len(sorted_df) * 35 + 100),
        margin=dict(l=80, r=40, t=50, b=40),
    )
    return fig


def gate_summary_chart(df: pd.DataFrame) -> go.Figure:
    """Visual summary of quality gate pass/fail by stock."""
    gate_cols = [c for c in df.columns if c.startswith("gate_") and c != "gate_pass"]
    gate_labels = {
        "gate_roic": "ROIC",
        "gate_roe": "ROE",
        "gate_leverage": "Leverage",
        "gate_fcf": "FCF > 0",
        "gate_gross_margin": "Gross Margin",
    }

    tickers = df.index.tolist()
    z_data = []
    for col in gate_cols:
        row = [1 if v else 0 for v in df[col]]
        z_data.append(row)

    # Custom colorscale: red for fail, green for pass
    fig = go.Figure(data=go.Heatmap(
        z=z_data,
        x=tickers,
        y=[gate_labels.get(c, c) for c in gate_cols],
        colorscale=[[0, "#e74c3c"], [1, "#2ecc71"]],
        showscale=False,
        text=[["PASS" if v else "FAIL" for v in df[col]] for col in gate_cols],
        texttemplate="%{text}",
        textfont=dict(size=11, color="white"),
    ))

    fig.update_layout(
        title=dict(text="Quality Gate Results", x=0.5, font=dict(size=16)),
        height=max(250, len(gate_cols) * 50 + 100),
        margin=dict(l=100, r=40, t=50, b=60),
        xaxis=dict(tickangle=45),
    )
    return fig


# ─────────────────────────────────────────────
# STREAMLIT UI
# ─────────────────────────────────────────────

def format_pct(val, decimals=1):
    if pd.isna(val):
        return "—"
    return f"{val:.{decimals}f}%"

def format_num(val, decimals=1):
    if pd.isna(val):
        return "—"
    return f"{val:.{decimals}f}"

def format_mcap(val):
    if pd.isna(val):
        return "—"
    if val >= 1e12:
        return f"${val/1e12:.1f}T"
    elif val >= 1e9:
        return f"${val/1e9:.1f}B"
    elif val >= 1e6:
        return f"${val/1e6:.0f}M"
    return f"${val:,.0f}"


def main():
    st.set_page_config(page_title="Stock Factor Screener", layout="wide",
                       page_icon="🔍")

    st.title("🔍 Stock Factor Screener")
    st.caption("Quality + Growth scoring model  •  Data: Yahoo Finance (Refinitiv/LSEG)")

    # ─── Sidebar ───
    with st.sidebar:
        st.header("⚙️ Configuration")

        # Ticker Input
        st.subheader("1. Universe Selection")
        watchlist_choice = st.selectbox("Load watchlist:",
                                         list(WATCHLISTS.keys()))
        default_tickers = ", ".join(WATCHLISTS.get(watchlist_choice, []))

        ticker_input = st.text_area(
            "Tickers (comma-separated):",
            value=default_tickers,
            height=80,
            help="Enter tickers to screen. These should be names "
                 "from the same theme/sector for meaningful relative ranking."
        )

        # Quality Gate Thresholds
        st.subheader("2. Quality Gate Thresholds")
        gates = {}
        gates["roic_min"] = st.slider("Min ROIC (%)", 0.0, 30.0,
                                       DEFAULT_QUALITY_GATES["roic_min"], 1.0)
        gates["roe_min"] = st.slider("Min ROE (%)", 0.0, 30.0,
                                      DEFAULT_QUALITY_GATES["roe_min"], 1.0)
        gates["net_debt_ebitda_max"] = st.slider("Max Net Debt/EBITDA (x)", 0.0, 10.0,
                                                  DEFAULT_QUALITY_GATES["net_debt_ebitda_max"], 0.5)
        gates["fcf_positive"] = st.checkbox("Require Positive FCF",
                                             value=DEFAULT_QUALITY_GATES["fcf_positive"])
        gates["gross_margin_min"] = st.slider("Min Gross Margin (%)", 0.0, 60.0,
                                               DEFAULT_QUALITY_GATES["gross_margin_min"], 5.0)

        # Scoring Weights
        st.subheader("3. Scoring Weights")
        st.caption("Must sum to 100%")
        w_prof = st.slider("Profitability", 0, 50, 25, 5)
        w_grow = st.slider("Growth", 0, 50, 30, 5)
        w_health = st.slider("Fin. Health", 0, 50, 20, 5)
        w_val = st.slider("Valuation", 0, 50, 15, 5)
        w_mom = st.slider("Momentum", 0, 50, 10, 5)
        total_w = w_prof + w_grow + w_health + w_val + w_mom

        if total_w != 100:
            st.warning(f"Weights sum to {total_w}% — must be 100%")
            weights_valid = False
        else:
            weights_valid = True

        weights = {
            "profitability": w_prof / 100,
            "growth": w_grow / 100,
            "financial_health": w_health / 100,
            "valuation": w_val / 100,
            "momentum": w_mom / 100,
        }

        # Display options
        st.subheader("4. Display")
        show_failed = st.checkbox("Show stocks that failed quality gate", value=True)

        run = st.button("🚀 Run Screener", type="primary",
                         use_container_width=True, disabled=not weights_valid)

    # ─── Main Content ───
    if not run:
        st.info("Configure your universe and parameters in the sidebar, then click **Run Screener**.")

        # Show methodology
        with st.expander("📖 Methodology", expanded=True):
            st.markdown("""
**Two-stage process:**

**Stage 1 — Quality Gate (Pass/Fail)**
Binary filters that eliminate low-quality names before scoring.
Every stock must clear all gates to advance to scoring.

| Gate | Default | Rationale |
|------|---------|-----------|
| ROIC | ≥ 15% | Capital allocation efficiency — the single best profitability metric |
| ROE | ≥ 15% | Equity returns floor |
| Net Debt/EBITDA | ≤ 3.0x | Leverage ceiling — avoids balance sheet risk |
| FCF | > 0 | Must generate real cash, not just accounting profits |
| Gross Margin | ≥ 30% | Moat proxy — pricing power and competitive advantage |

**Stage 2 — Multi-Factor Score (0-100)**
Percentile ranking *within the input universe* across five dimensions:

| Dimension | Weight | Key Metrics |
|-----------|--------|-------------|
| Profitability | 25% | ROIC, ROE, Operating Margin, FCF Margin |
| Growth | 30% | Revenue YoY, Revenue 3Y CAGR, Earnings Growth |
| Financial Health | 20% | Net Debt/EBITDA, Current Ratio, Interest Coverage |
| Valuation | 15% | PEG, Forward P/E, EV/EBITDA |
| Momentum | 10% | 3M Return, 6M Return, Analyst Target Upside |

**Important:** Scores are *relative* within the input group. A score of 80 means
"better than 80% of the stocks you entered" — not an absolute rating.
Feed in stocks from the *same theme* for meaningful comparison.
            """)
        return

    # Parse tickers
    tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]
    if len(tickers) < 2:
        st.error("Enter at least 2 tickers for meaningful relative scoring.")
        return

    # Fetch data
    st.subheader(f"Screening {len(tickers)} stocks...")
    progress = st.progress(0)
    df = fetch_batch(tickers, progress_callback=progress.progress)
    progress.empty()

    # Filter out errors
    valid_mask = df["data_quality"] == "full"
    errors = df[~valid_mask]
    df = df[valid_mask]

    if not errors.empty:
        st.warning(f"Could not fetch data for: {', '.join(errors.index.tolist())}")

    if len(df) < 2:
        st.error("Need at least 2 valid stocks to score. Check tickers and retry.")
        return

    # Stage 1: Quality Gate
    df = apply_quality_gate(df, gates)
    passed = df[df["gate_pass"]]
    failed = df[~df["gate_pass"]]

    # Display gate results
    st.subheader("Stage 1: Quality Gate")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Screened", len(df))
    col2.metric("Passed", len(passed), delta=None)
    col3.metric("Failed", len(failed),
                delta=f"-{len(failed)}" if len(failed) > 0 else None,
                delta_color="inverse")

    st.plotly_chart(gate_summary_chart(df), use_container_width=True)

    if show_failed and not failed.empty:
        with st.expander(f"❌ Failed stocks ({len(failed)})"):
            fail_display = failed[["name", "roic", "roe", "gross_margin",
                                    "net_debt_ebitda", "fcf", "gates_passed",
                                    "gates_total"]].copy()
            fail_display.columns = ["Name", "ROIC%", "ROE%", "Gross Margin%",
                                     "Net Debt/EBITDA", "FCF", "Gates Passed", "Total"]
            st.dataframe(fail_display, use_container_width=True)

    if len(passed) < 2:
        st.warning("Fewer than 2 stocks passed the quality gate. "
                    "Scoring requires relative comparison — showing "
                    "individual metrics only.")
        if len(passed) == 1:
            st.dataframe(passed.T, use_container_width=True)
        return

    # Stage 2: Scoring
    st.subheader("Stage 2: Factor Scoring")
    scores = compute_composite_score(passed, weights)

    # Merge scores with fundamentals for display
    display = pd.concat([
        passed[["name", "sector", "market_cap", "price",
                 "roic", "roe", "gross_margin", "operating_margin", "fcf_margin",
                 "rev_growth_yoy", "rev_cagr_3y", "earnings_growth",
                 "net_debt_ebitda", "forward_pe", "peg", "ev_ebitda",
                 "return_3m", "return_6m", "analyst_target_upside",
                 "recommendation", "num_analysts"]],
        scores
    ], axis=1).sort_values("rank")

    # Summary cards for top picks
    top = display.head(3)
    st.markdown("### 🏆 Top Ranked")
    cols = st.columns(min(3, len(top)))
    for i, (ticker, row) in enumerate(top.iterrows()):
        with cols[i]:
            st.markdown(f"**#{int(row['rank'])} — {ticker}**")
            st.caption(row["name"])
            st.metric("Composite Score", f"{row['composite']:.1f}")
            st.caption(f"Mkt Cap: {format_mcap(row['market_cap'])}")
            st.caption(f"ROIC: {format_pct(row['roic'])} | "
                       f"Rev Growth: {format_pct(row['rev_growth_yoy'])}")
            st.caption(f"Fwd P/E: {format_num(row['forward_pe'])} | "
                       f"PEG: {format_num(row['peg'])}")

    # Charts
    tab1, tab2, tab3 = st.tabs(["📊 Score Ranking", "🕸️ Factor Profile", "📋 Full Data"])

    with tab1:
        st.plotly_chart(score_bar_chart(scores), use_container_width=True)

        # Dimension breakdown
        st.markdown("#### Dimension Breakdown")
        dim_display = scores[["profitability", "growth", "financial_health",
                               "valuation", "momentum", "composite", "rank"]].copy()
        dim_display.columns = ["Profitability", "Growth", "Fin. Health",
                                "Valuation", "Momentum", "Composite", "Rank"]
        dim_display = dim_display.sort_values("Rank")

        # Color-code the scores
        st.dataframe(
            dim_display.style.background_gradient(
                cmap="RdYlGn", subset=["Profitability", "Growth", "Fin. Health",
                                        "Valuation", "Momentum", "Composite"],
                vmin=0, vmax=100
            ).format("{:.1f}", subset=["Profitability", "Growth", "Fin. Health",
                                        "Valuation", "Momentum", "Composite"]
            ).format("{:.0f}", subset=["Rank"]),
            use_container_width=True
        )

    with tab2:
        # Select stocks to compare
        compare_tickers = st.multiselect(
            "Select stocks to compare (max 5):",
            scores.index.tolist(),
            default=scores.sort_values("composite", ascending=False).index[:3].tolist(),
            max_selections=5
        )
        if compare_tickers:
            st.plotly_chart(radar_chart(scores, compare_tickers),
                           use_container_width=True)

    with tab3:
        st.markdown("#### Raw Fundamentals (Quality Gate Survivors)")

        # Format for display
        raw = display.copy()
        format_cols = {
            "roic": format_pct, "roe": format_pct,
            "gross_margin": format_pct, "operating_margin": format_pct,
            "fcf_margin": format_pct, "rev_growth_yoy": format_pct,
            "rev_cagr_3y": format_pct, "earnings_growth": format_pct,
            "return_3m": format_pct, "return_6m": format_pct,
            "analyst_target_upside": format_pct,
            "net_debt_ebitda": lambda x: format_num(x, 2),
            "forward_pe": lambda x: format_num(x, 1),
            "peg": lambda x: format_num(x, 2),
            "ev_ebitda": lambda x: format_num(x, 1),
            "market_cap": format_mcap,
            "price": lambda x: f"${x:.2f}" if pd.notna(x) else "—",
            "composite": lambda x: f"{x:.1f}",
        }
        for col, fmt in format_cols.items():
            if col in raw.columns:
                raw[col] = raw[col].apply(fmt)

        st.dataframe(raw, use_container_width=True)

        # Download
        csv = display.to_csv()
        st.download_button("📥 Download Full Data (CSV)", csv,
                           "screener_results.csv", "text/csv")

    # Methodology reminder
    with st.expander("⚠️ Limitations & Caveats"):
        st.markdown("""
- **Relative scoring:** Scores rank stocks *within this input group only*. 
  A 90/100 in a weak universe doesn't mean the stock is objectively great.
- **Data freshness:** Yahoo Finance data can lag by 1-2 days for prices 
  and up to a quarter for fundamentals (depends on filing dates).
- **Missing data:** When a metric is unavailable, the score defaults to 50 
  (neutral). Check the raw data tab for "—" entries.
- **No forward estimates beyond consensus:** The screen uses trailing 
  financials and analyst consensus. It doesn't capture thesis-specific 
  catalysts — that's *your* job in the diligence step.
- **Sector-agnostic:** Valuation norms differ by sector. A 30x P/E is 
  expensive for a bank but cheap for high-growth SaaS. Use within-theme 
  comparisons for best results.
        """)


if __name__ == "__main__":
    main()
