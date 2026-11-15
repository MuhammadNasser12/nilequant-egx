import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
import urllib.request
import json
import os

# 1. Page Configuration
st.set_page_config(
    page_title="NILEQUANT | EGX Quantitative Terminal",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Helper function to read secrets silently from Environment (GitHub) or Streamlit Secrets
def get_cloud_secret(key, default=""):
    val = os.environ.get(key)
    if val:
        return val
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return default

SENDER_EMAIL = get_cloud_secret("SENDER_EMAIL")
APP_PASSWORD = get_cloud_secret("APP_PASSWORD")
RECEIVER_EMAIL = get_cloud_secret("RECEIVER_EMAIL", SENDER_EMAIL)

# Permanently locked to ACCUMULATE & STRONG BUY (score >= 1) and Auto-Dispatch ON
MIN_SCORE_FOR_EMAIL = 1
AUTO_EMAIL_ENABLED = True

# 2. Institutional Custom CSS & Visual Identity
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        background-color: #0B0F19;
        color: #E5E7EB;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {background: transparent !important;}

    .terminal-header {
        background: linear-gradient(90deg, #111827 0%, #1E293B 100%);
        border: 1px solid #1F2937;
        border-left: 4px solid #3B82F6;
        padding: 20px 26px;
        border-radius: 6px;
        margin-bottom: 24px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 12px;
    }
    .brand-title {
        font-size: 1.5rem;
        font-weight: 700;
        letter-spacing: 1.5px;
        color: #F9FAFB;
        margin: 0;
    }
    .brand-accent {
        color: #3B82F6;
    }
    .brand-subtitle {
        font-size: 0.82rem;
        color: #9CA3AF;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-top: 4px;
    }
    .terminal-badge {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        background-color: #1F2937;
        color: #10B981;
        border: 1px solid #374151;
        padding: 6px 12px;
        border-radius: 4px;
        letter-spacing: 0.5px;
    }

    .section-header {
        font-size: 0.95rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1.2px;
        color: #9CA3AF;
        border-bottom: 1px solid #1F2937;
        padding-bottom: 8px;
        margin-top: 16px;
        margin-bottom: 16px;
    }

    div[data-testid="stMetric"] {
        background-color: #111827;
        border: 1px solid #1F2937;
        border-top: 2px solid #3B82F6;
        padding: 16px 18px;
        border-radius: 6px;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.78rem !important;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        color: #9CA3AF !important;
    }
    div[data-testid="stMetricValue"] {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.45rem !important;
        font-weight: 600;
        color: #F9FAFB !important;
    }

    .signal-item {
        background-color: #111827;
        border: 1px solid #1F2937;
        padding: 10px 14px;
        border-radius: 4px;
        margin-bottom: 8px;
        font-size: 0.9rem;
        display: flex;
        align-items: center;
    }
    .tag-bullish {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 600;
        color: #10B981;
        background-color: rgba(16, 185, 129, 0.12);
        border: 1px solid rgba(16, 185, 129, 0.3);
        padding: 2px 8px;
        border-radius: 3px;
        margin-right: 12px;
        min-width: 78px;
        text-align: center;
    }
    .tag-bearish {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 600;
        color: #EF4444;
        background-color: rgba(239, 68, 68, 0.12);
        border: 1px solid rgba(239, 68, 68, 0.3);
        padding: 2px 8px;
        border-radius: 3px;
        margin-right: 12px;
        min-width: 78px;
        text-align: center;
    }

    .institutional-alert {
        background-color: rgba(16, 185, 129, 0.08);
        border: 1px solid rgba(16, 185, 129, 0.4);
        border-left: 4px solid #10B981;
        padding: 14px 18px;
        border-radius: 4px;
        margin-top: 12px;
        margin-bottom: 12px;
        color: #E5E7EB;
        font-size: 0.9rem;
    }

    section[data-testid="stSidebar"] {
        background-color: #0D131F;
        border-right: 1px solid #1F2937;
    }
    </style>
""", unsafe_allow_html=True)

# 3. Egyptian Exchange (EGX) Sectors & Equities Database
EGX_SECTORS = {
    "Banking & Financial Services": {
        "COMI.CA": "Commercial International Bank (CIB)",
        "HRHO.CA": "EFG Holding",
        "CIEB.CA": "Credit Agricole Egypt",
        "ADIB.CA": "Abu Dhabi Islamic Bank Egypt",
        "FAIT.CA": "Faisal Islamic Bank of Egypt"
    },
    "Real Estate & Construction": {
        "TMGH.CA": "Talaat Moustafa Group Holding",
        "PHDC.CA": "Palm Hills Developments",
        "EMFD.CA": "Emaar Misr for Development",
        "HELI.CA": "Heliopolis Housing & Development",
        "MASR.CA": "Madinet Masr for Housing & Development"
    },
    "IT, Telecom & Fintech": {
        "FWRY.CA": "Fawry for Banking Technology",
        "ETEL.CA": "Telecom Egypt",
        "EFIH.CA": "e-finance for Digital Investments",
        "RAYA.CA": "Raya Holding for Financial Investments"
    },
    "Petrochemicals & Fertilizers": {
        "ABUK.CA": "Abu Qir Fertilizers",
        "MFPC.CA": "Misr Fertilizers Production (MOPCO)",
        "SKPC.CA": "Sidi Kerir Petrochemicals (Sidpec)",
        "AMOC.CA": "Alexandria Mineral Oils Company (AMOC)"
    },
    "Industrial & Basic Resources": {
        "SWDY.CA": "Elsewedy Electric",
        "ESRS.CA": "Ezz Steel",
        "EGAL.CA": "Egypt Aluminum",
        "ORWE.CA": "Oriental Weavers"
    },
    "Food, Healthcare & Pharmaceuticals": {
        "EFID.CA": "Edita Food Industries",
        "JUFO.CA": "Juhayna Food Industries",
        "ISPH.CA": "Ibnsina Pharma",
        "PHAR.CA": "EIPICO Pharmaceuticals"
    }
}

ALL_STOCKS = {ticker: name for sector in EGX_SECTORS.values() for ticker, name in sector.items()}
WATCHLIST_FILE = "watchlist.json"

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                return [t for t in saved if t in ALL_STOCKS]
        except Exception:
            pass
    return ["COMI.CA", "FWRY.CA", "TMGH.CA"]

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False)

if "notified_stocks" not in st.session_state:
    st.session_state["notified_stocks"] = set()

# 4. Institutional Email Alert Dispatch
def send_buy_alert_email(buy_opportunities):
    if not SENDER_EMAIL or not APP_PASSWORD or not RECEIVER_EMAIL:
        return False, "Cloud SMTP Secrets not detected in environment."
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "NILEQUANT SIGNAL ALERT: Actionable Buy Signal on EGX"
        msg["From"] = SENDER_EMAIL
        msg["To"] = RECEIVER_EMAIL

        rows_html = ""
        for item in buy_opportunities:
            rows_html += f"""
            <tr style="border-bottom: 1px solid #E5E7EB; text-align: center; font-size: 13px;">
                <td style="padding: 12px; font-family: monospace; font-weight: 700; color: #111827;">{item['Ticker']}</td>
                <td style="padding: 12px; text-align: left; color: #374151;">{item['Company Name']}</td>
                <td style="padding: 12px; font-family: monospace; font-weight: 700; color: #111827;">{item['Price (EGP)']:.2f} EGP</td>
                <td style="padding: 12px; font-weight: 700; color: #059669;">{item['Signal']}</td>
                <td style="padding: 12px; font-family: monospace; color: #DC2626;">{item['Stop Loss']:.2f} EGP</td>
                <td style="padding: 12px; font-family: monospace; font-weight: 700; color: #2563EB;">{item['Target Price']:.2f} EGP</td>
            </tr>
            """

        html_content = f"""
        <div style="font-family: 'Segoe UI', Arial, sans-serif; background-color: #F3F4F6; padding: 28px;">
            <div style="max-width: 700px; margin: 0 auto; background-color: #FFFFFF; border: 1px solid #D1D5DB; border-top: 4px solid #2563EB; border-radius: 4px; padding: 24px;">
                <h2 style="margin: 0 0 6px 0; color: #111827; font-size: 18px; letter-spacing: 0.5px;">NILEQUANT | EGX QUANTITATIVE ADVISORY</h2>
                <p style="margin: 0 0 20px 0; font-size: 12px; color: #6B7280; text-transform: uppercase; letter-spacing: 1px;">Automated Technical Signal Notification</p>
                <p style="font-size: 14px; color: #374151; line-height: 1.5;">
                    Quantitative screening has identified an actionable <strong>ACCUMULATE / STRONG BUY</strong> signal on the following watchlist equities:
                </p>
                <table style="width: 100%; border-collapse: collapse; margin-top: 16px;">
                    <thead>
                        <tr style="background-color: #111827; color: #F9FAFB; text-align: center; font-size: 12px; text-transform: uppercase;">
                            <th style="padding: 10px;">Ticker</th>
                            <th style="padding: 10px; text-align: left;">Company</th>
                            <th style="padding: 10px;">Last Price</th>
                            <th style="padding: 10px;">Signal</th>
                            <th style="padding: 10px;">Stop Loss</th>
                            <th style="padding: 10px;">Target</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>
        </div>
        """

        msg.attach(MIMEText(html_content, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        return True, "Alert notification dispatched automatically."
    except Exception as e:
        return False, f"SMTP Dispatch Error: {e}"

# 5. Live Intraday Feed Engine (TradingView Egypt Scanner + Yahoo 5m Intraday)
@st.cache_data(ttl=45)
def fetch_live_tv_quotes():
    tv_tickers = [f"EGX:{t.replace('.CA', '')}" for t in ALL_STOCKS.keys()]
    payload = {
        "symbols": {"tickers": tv_tickers, "query": {"types": []}},
        "columns": ["close", "change", "open", "high", "low", "volume"]
    }
    try:
        req = urllib.request.Request(
            "https://scanner.tradingview.com/egypt/scan",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        quotes = {}
        for row in result.get("data", []):
            sym = row.get("s", "").replace("EGX:", "") + ".CA"
            d = row.get("d", [])
            if len(d) >= 5 and d[0] is not None:
                quotes[sym] = {
                    "close": float(d[0]),
                    "change_pct": float(d[1]) if d[1] is not None else None,
                    "open": float(d[2]) if d[2] is not None else float(d[0]),
                    "high": float(d[3]) if d[3] is not None else float(d[0]),
                    "low": float(d[4]) if d[4] is not None else float(d[0]),
                }
        return quotes
    except Exception:
        return {}

@st.cache_data(ttl=45)
def fetch_stock_data(ticker, period="6mo"):
    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna().copy()

        tv_quotes = fetch_live_tv_quotes()
        if ticker in tv_quotes:
            q = tv_quotes[ticker]
            df.iloc[-1, df.columns.get_loc("Close")] = q["close"]
            df.iloc[-1, df.columns.get_loc("High")] = max(float(df["High"].iloc[-1]), q["high"])
            df.iloc[-1, df.columns.get_loc("Low")] = min(float(df["Low"].iloc[-1]), q["low"])
        else:
            intraday = yf.download(ticker, period="5d", interval="5m", progress=False)
            if not intraday.empty:
                if isinstance(intraday.columns, pd.MultiIndex):
                    intraday.columns = intraday.columns.get_level_values(0)
                last_live_price = float(intraday["Close"].dropna().iloc[-1])
                df.iloc[-1, df.columns.get_loc("Close")] = last_live_price

        return df
    except Exception:
        return None

def calculate_indicators(df):
    data = df.copy()
    data['SMA20'] = data['Close'].rolling(window=20).mean()
    data['SMA50'] = data['Close'].rolling(window=50).mean()
    
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    data['RSI'] = 100 - (100 / (1 + rs))
    
    ema12 = data['Close'].ewm(span=12, adjust=False).mean()
    ema26 = data['Close'].ewm(span=26, adjust=False).mean()
    data['MACD'] = ema12 - ema26
    data['Signal_Line'] = data['MACD'].ewm(span=9, adjust=False).mean()
    
    high_low = data['High'] - data['Low']
    high_close = np.abs(data['High'] - data['Close'].shift())
    low_close = np.abs(data['Low'] - data['Close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    data['ATR'] = tr.rolling(window=14).mean()
    
    return data

# 6. Quantitative Signal Engine
def generate_recommendation(df):
    if df is None or len(df) < 50:
        return "INSUFFICIENT DATA", 0, [], 0.0, 0.0

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    score = 0
    reasons = []
    
    if latest['RSI'] < 30:
        score += 2
        reasons.append(("BULLISH", f"RSI-14 is in deep oversold territory ({latest['RSI']:.1f}), indicating high probability of mean reversion."))
    elif latest['RSI'] < 45 and latest['RSI'] > prev['RSI']:
        score += 1
        reasons.append(("BULLISH", f"RSI-14 is recovering upward from lower range ({latest['RSI']:.1f})."))
    elif latest['RSI'] > 70:
        score -= 2
        reasons.append(("BEARISH", f"RSI-14 has reached overbought territory ({latest['RSI']:.1f}), elevating short-term pullback risk."))

    if latest['Close'] > latest['SMA20'] and latest['SMA20'] > latest['SMA50']:
        score += 2
        reasons.append(("BULLISH", "Price is trading above both SMA-20 and SMA-50, confirming positive trend alignment."))
    elif latest['Close'] > latest['SMA20']:
        score += 1
        reasons.append(("BULLISH", "Price is holding above the 20-day Moving Average (short-term trend support)."))
    elif latest['Close'] < latest['SMA20'] and latest['SMA20'] < latest['SMA50']:
        score -= 2
        reasons.append(("BEARISH", "Price is trading below both SMA-20 and SMA-50, confirming downward trend pressure."))

    if latest['MACD'] > latest['Signal_Line'] and prev['MACD'] <= prev['Signal_Line']:
        score += 2
        reasons.append(("BULLISH", "MACD line crossed above the Signal line (fresh positive momentum trigger)."))
    elif latest['MACD'] > latest['Signal_Line']:
        score += 1
        reasons.append(("BULLISH", "MACD remains in positive territory above the Signal line."))
    elif latest['MACD'] < latest['Signal_Line'] and prev['MACD'] >= prev['Signal_Line']:
        score -= 2
        reasons.append(("BEARISH", "MACD line crossed below the Signal line (negative momentum breakdown)."))
    else:
        score -= 1
        reasons.append(("BEARISH", "MACD histogram remains negative below the Signal line."))

    if score >= 3:
        decision = "STRONG BUY"
    elif score >= 1:
        decision = "ACCUMULATE"
    elif score == 0:
        decision = "HOLD / NEUTRAL"
    elif score >= -2:
        decision = "REDUCE"
    else:
        decision = "STRONG SELL"

    atr = latest['ATR'] if not np.isnan(latest['ATR']) else latest['Close'] * 0.03
    stop_loss = latest['Close'] - (1.5 * atr)
    take_profit = latest['Close'] + (3.0 * atr)

    return decision, score, reasons, stop_loss, take_profit

def style_dataframe(df):
    def color_signal(val):
        if val == "STRONG BUY":
            return "background-color: rgba(16, 185, 129, 0.18); color: #10B981; font-weight: 700;"
        elif val == "ACCUMULATE":
            return "background-color: rgba(16, 185, 129, 0.08); color: #34D399; font-weight: 600;"
        elif val == "HOLD / NEUTRAL":
            return "color: #9CA3AF; font-weight: 500;"
        elif val == "REDUCE":
            return "background-color: rgba(239, 68, 68, 0.08); color: #F87171; font-weight: 600;"
        elif val == "STRONG SELL":
            return "background-color: rgba(239, 68, 68, 0.18); color: #EF4444; font-weight: 700;"
        return ""

    def color_change(val):
        if isinstance(val, (int, float)):
            if val > 0:
                return "color: #10B981; font-weight: 600;"
            elif val < 0:
                return "color: #EF4444; font-weight: 600;"
        return "color: #9CA3AF;"

    return (
        df.style
        .map(color_signal, subset=["Signal"])
        .map(color_change, subset=["Daily Change %"])
        .format({
            "Price (EGP)": "{:.2f}",
            "Daily Change %": "{:+.2f}%",
            "RSI (14)": "{:.1f}",
            "Stop Loss": "{:.2f}",
            "Target Price": "{:.2f}"
        })
    )

def is_egx_market_open(now_cairo):
    is_trading_day = now_cairo.weekday() in (6, 0, 1, 2, 3)
    market_open = now_cairo.replace(hour=10, minute=0, second=0, microsecond=0)
    market_close = now_cairo.replace(hour=14, minute=30, second=0, microsecond=0)
    return is_trading_day and (market_open <= now_cairo <= market_close)

# 7. Sidebar Navigation & Controls (Clean — No Email Inputs)
st.sidebar.markdown("### DATA SYNCHRONIZATION")
if st.sidebar.button("Force Refresh Market Data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

auto_refresh = st.sidebar.checkbox("Auto-Refresh Feed (Every 2 Min)", value=True)
refresh_interval = 120 if auto_refresh else None

st.sidebar.divider()
st.sidebar.markdown("### WATCHLIST CONFIGURATION")
current_watchlist = load_watchlist()
selected_favorites = st.sidebar.multiselect(
    "Monitored Equities",
    options=list(ALL_STOCKS.keys()),
    default=current_watchlist,
    format_func=lambda x: f"{x.replace('.CA', '')} — {ALL_STOCKS[x]}"
)

if selected_favorites != current_watchlist:
    save_watchlist(selected_favorites)

st.sidebar.divider()
st.sidebar.markdown("### SECTOR & CHART PARAMETERS")
selected_sector = st.sidebar.selectbox("Market Sector", list(EGX_SECTORS.keys()))
sector_stocks = EGX_SECTORS[selected_sector]

selected_ticker = st.sidebar.selectbox(
    "Target Equity",
    options=list(sector_stocks.keys()),
    format_func=lambda x: f"{x.replace('.CA', '')} — {sector_stocks[x]}"
)
period_map = {"3 Months": "3mo", "6 Months": "6mo", "1 Year": "1y", "2 Years": "2y"}
selected_period_label = st.sidebar.select_slider("Historical Horizon", options=list(period_map.keys()), value="6 Months")
selected_period = period_map[selected_period_label]

# 8. Main Auto-Refreshing Terminal Body
@st.fragment(run_every=refresh_interval)
def render_live_terminal():
    cairo_tz = timezone(timedelta(hours=2))
    now_cairo = datetime.now(cairo_tz)
    sync_time = now_cairo.strftime("%H:%M:%S EET")
    session_status = "OPEN (LIVE)" if is_egx_market_open(now_cairo) else "CLOSED (EOD)"
    tv_quotes = fetch_live_tv_quotes()

    st.markdown(f"""
        <div class="terminal-header">
            <div>
                <p class="brand-title">NILE<span class="brand-accent">QUANT</span></p>
                <p class="brand-subtitle">Egyptian Exchange (EGX) Quantitative Signal & Advisory Terminal</p>
            </div>
            <div class="terminal-badge">SESSION: {session_status} | LAST SYNC: {sync_time}</div>
        </div>
    """, unsafe_allow_html=True)

    # --- Section 1: Watchlist Monitor ---
    st.markdown('<div class="section-header">01 / Watchlist Signal Monitor</div>', unsafe_allow_html=True)

    if selected_favorites:
        fav_summary = []
        urgent_buy_list = []

        with st.spinner("Synchronizing live EGX market feed..."):
            for ticker in selected_favorites:
                name = ALL_STOCKS[ticker]
                raw_df = fetch_stock_data(ticker, period="6mo")
                if raw_df is not None and len(raw_df) >= 50:
                    ind_df = calculate_indicators(raw_df)
                    decision, score, _, sl, tp = generate_recommendation(ind_df)
                    last_close = float(ind_df['Close'].iloc[-1])
                    prev_close = float(ind_df['Close'].iloc[-2])
                    
                    if ticker in tv_quotes and tv_quotes[ticker]["change_pct"] is not None:
                        change_pct = tv_quotes[ticker]["change_pct"]
                    else:
                        change_pct = ((last_close - prev_close) / prev_close) * 100

                    item_data = {
                        "Ticker": ticker.replace(".CA", ""),
                        "Company Name": name,
                        "Price (EGP)": round(last_close, 2),
                        "Daily Change %": round(change_pct, 2),
                        "RSI (14)": round(float(ind_df['RSI'].iloc[-1]), 1),
                        "Signal": decision,
                        "Stop Loss": round(float(sl), 2),
                        "Target Price": round(float(tp), 2),
                        "score": score
                    }
                    fav_summary.append(item_data)

                    # Trigger on ACCUMULATE & STRONG BUY (score >= 1)
                    if score >= MIN_SCORE_FOR_EMAIL:
                        urgent_buy_list.append(item_data)

        if fav_summary:
            fav_df = pd.DataFrame(fav_summary).drop(columns=["score"])
            st.dataframe(style_dataframe(fav_df), use_container_width=True, hide_index=True)

            if urgent_buy_list:
                buy_names = ", ".join([f"{x['Ticker']} ({x['Signal']})" for x in urgent_buy_list])
                st.markdown(
                    f'<div class="institutional-alert"><strong>ACTIONABLE SIGNAL DETECTED:</strong> '
                    f'Quantitative criteria met for accumulation on: {buy_names}</div>',
                    unsafe_allow_html=True
                )

                new_alerts = [x for x in urgent_buy_list if x['Ticker'] not in st.session_state["notified_stocks"]]
                if AUTO_EMAIL_ENABLED and new_alerts and SENDER_EMAIL and APP_PASSWORD:
                    success, _ = send_buy_alert_email(new_alerts)
                    if success:
                        for x in new_alerts:
                            st.session_state["notified_stocks"].add(x['Ticker'])
    else:
        st.info("No equities currently assigned to Watchlist. Select tickers from the left configuration panel.")

    # --- Section 2: Sector Screener ---
    st.markdown(f'<div class="section-header">02 / Sector Quantitative Screener — {selected_sector}</div>', unsafe_allow_html=True)

    sector_summary = []
    with st.spinner("Computing sector metrics..."):
        for ticker, name in sector_stocks.items():
            raw_df = fetch_stock_data(ticker, period="6mo")
            if raw_df is not None and len(raw_df) >= 50:
                ind_df = calculate_indicators(raw_df)
                decision, score, _, sl, tp = generate_recommendation(ind_df)
                last_close = float(ind_df['Close'].iloc[-1])
                prev_close = float(ind_df['Close'].iloc[-2])

                if ticker in tv_quotes and tv_quotes[ticker]["change_pct"] is not None:
                    change_pct = tv_quotes[ticker]["change_pct"]
                else:
                    change_pct = ((last_close - prev_close) / prev_close) * 100
                
                sector_summary.append({
                    "Ticker": ticker.replace(".CA", ""),
                    "Company Name": name,
                    "Price (EGP)": round(last_close, 2),
                    "Daily Change %": round(change_pct, 2),
                    "RSI (14)": round(float(ind_df['RSI'].iloc[-1]), 1),
                    "Signal": decision,
                    "Stop Loss": round(float(sl), 2),
                    "Target Price": round(float(tp), 2)
                })

    if sector_summary:
        summary_df = pd.DataFrame(sector_summary)
        st.dataframe(style_dataframe(summary_df), use_container_width=True, hide_index=True)

    # --- Section 3: Single-Equity Deep Dive ---
    stock_name = sector_stocks[selected_ticker]
    clean_ticker = selected_ticker.replace('.CA', '')
    st.markdown(f'<div class="section-header">03 / Technical Deep-Dive — {clean_ticker} ({stock_name})</div>', unsafe_allow_html=True)

    df_raw = fetch_stock_data(selected_ticker, period=selected_period)

    if df_raw is not None and len(df_raw) >= 50:
        df_ind = calculate_indicators(df_raw)
        decision, score, reasons, stop_loss, take_profit = generate_recommendation(df_ind)
        
        latest = df_ind.iloc[-1]
        prev = df_ind.iloc[-2]
        if selected_ticker in tv_quotes and tv_quotes[selected_ticker]["change_pct"] is not None:
            pct_change = tv_quotes[selected_ticker]["change_pct"]
        else:
            price_change = float(latest['Close'] - prev['Close'])
            pct_change = (price_change / float(prev['Close'])) * 100

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Last Close (EGP)", f"{latest['Close']:.2f}", f"{pct_change:+.2f}%")
        col2.metric("Model Signal", decision)
        col3.metric("RSI (14-Day)", f"{latest['RSI']:.1f}")
        col4.metric("ATR Stop Loss", f"{stop_loss:.2f} EGP")
        col5.metric("ATR Target Price", f"{take_profit:.2f} EGP")

        st.markdown("#### Factor Attribution Breakdown")
        for tag, text in reasons:
            tag_class = "tag-bullish" if tag == "BULLISH" else "tag-bearish"
            st.markdown(
                f'<div class="signal-item"><span class="{tag_class}">{tag}</span><span>{text}</span></div>',
                unsafe_allow_html=True
            )

        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            vertical_spacing=0.06,
            subplot_titles=(f"{clean_ticker} — Price Action & Moving Averages", "Relative Strength Index (14)"),
            row_heights=[0.72, 0.28]
        )

        fig.add_trace(go.Candlestick(
            x=df_ind.index, open=df_ind['Open'], high=df_ind['High'],
            low=df_ind['Low'], close=df_ind['Close'], name="OHLC",
            increasing_line_color='#10B981', decreasing_line_color='#EF4444'
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=df_ind.index, y=df_ind['SMA20'],
            line=dict(color='#3B82F6', width=1.5), name='SMA 20'
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=df_ind.index, y=df_ind['SMA50'],
            line=dict(color='#F59E0B', width=1.5), name='SMA 50'
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=df_ind.index, y=df_ind['RSI'],
            line=dict(color='#60A5FA', width=1.8), name='RSI (14)'
        ), row=2, col=1)

        fig.add_hline(y=70, line_dash="dot", line_color="#EF4444", row=2, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#10B981", row=2, col=1)

        fig.update_layout(
            height=640,
            paper_bgcolor="#111827",
            plot_bgcolor="#111827",
            font=dict(family="Inter, sans-serif", color="#9CA3AF", size=12),
            xaxis_rangeslider_visible=False,
            margin=dict(l=20, r=20, t=45, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        fig.update_xaxes(gridcolor="#1F2937", zeroline=False)
        fig.update_yaxes(gridcolor="#1F2937", zeroline=False)

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("Historical market data insufficient to compute quantitative factors for this equity.")

render_live_terminal()
