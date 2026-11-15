import yfinance as yf
import pandas as pd
import numpy as np
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import urllib.request
import json
import os

# Reads directly from GitHub Actions Secrets
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
APP_PASSWORD = os.environ.get("APP_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL") or SENDER_EMAIL

WATCHLIST_FILE = "watchlist.json"
SENT_LOG_FILE = "sent_alerts.json"

ALL_STOCKS = {
    "COMI.CA": "Commercial International Bank (CIB)",
    "HRHO.CA": "EFG Holding",
    "CIEB.CA": "Credit Agricole Egypt",
    "ADIB.CA": "Abu Dhabi Islamic Bank Egypt",
    "FAIT.CA": "Faisal Islamic Bank of Egypt",
    "TMGH.CA": "Talaat Moustafa Group Holding",
    "PHDC.CA": "Palm Hills Developments",
    "EMFD.CA": "Emaar Misr for Development",
    "HELI.CA": "Heliopolis Housing & Development",
    "MASR.CA": "Madinet Masr for Housing & Development",
    "FWRY.CA": "Fawry for Banking Technology",
    "ETEL.CA": "Telecom Egypt",
    "EFIH.CA": "e-finance for Digital Investments",
    "RAYA.CA": "Raya Holding for Financial Investments",
    "ABUK.CA": "Abu Qir Fertilizers",
    "MFPC.CA": "Misr Fertilizers Production (MOPCO)",
    "SKPC.CA": "Sidi Kerir Petrochemicals (Sidpec)",
    "AMOC.CA": "Alexandria Mineral Oils Company (AMOC)",
    "SWDY.CA": "Elsewedy Electric",
    "ESRS.CA": "Ezz Steel",
    "EGAL.CA": "Egypt Aluminum",
    "ORWE.CA": "Oriental Weavers",
    "EFID.CA": "Edita Food Industries",
    "JUFO.CA": "Juhayna Food Industries",
    "ISPH.CA": "Ibnsina Pharma",
    "PHAR.CA": "EIPICO Pharmaceuticals"
}

def fetch_live_tv_quotes():
    tv_tickers = [f"EGX:{t.replace('.CA', '')}" for t in ALL_STOCKS.keys()]
    payload = {
        "symbols": {"tickers": tv_tickers, "query": {"types": []}},
        "columns": ["close", "change", "open", "high", "low"]
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
                quotes[sym] = float(d[0])
        return quotes
    except Exception:
        return {}

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return ["COMI.CA", "FWRY.CA", "TMGH.CA"]

def load_sent_log():
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    if os.path.exists(SENT_LOG_FILE):
        try:
            with open(SENT_LOG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("date") == today_str:
                    return set(data.get("tickers", []))
        except Exception:
            pass
    return set()

def save_sent_log(tickers_set):
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    with open(SENT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump({"date": today_str, "tickers": list(tickers_set)}, f)

def evaluate_equity(ticker, tv_quotes):
    df = yf.download(ticker, period="6mo", interval="1d", progress=False)
    if df.empty or len(df) < 50:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna().copy()

    if ticker in tv_quotes:
        df.iloc[-1, df.columns.get_loc("Close")] = tv_quotes[ticker]

    df['SMA20'] = df['Close'].rolling(window=20).mean()
    df['SMA50'] = df['Close'].rolling(window=50).mean()

    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df['RSI'] = 100 - (100 / (1 + rs))

    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()

    high_low = df['High'] - data_low if 'data_low' in locals() else df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    score = 0

    if latest['RSI'] < 30: score += 2
    elif latest['RSI'] < 45 and latest['RSI'] > prev['RSI']: score += 1
    elif latest['RSI'] > 70: score -= 2

    if latest['Close'] > latest['SMA20'] and latest['SMA20'] > latest['SMA50']: score += 2
    elif latest['Close'] > latest['SMA20']: score += 1
    elif latest['Close'] < latest['SMA20'] and latest['SMA20'] < latest['SMA50']: score -= 2

    if latest['MACD'] > latest['Signal_Line'] and prev['MACD'] <= prev['Signal_Line']: score += 2
    elif latest['MACD'] > latest['Signal_Line']: score += 1
    elif latest['MACD'] < latest['Signal_Line'] and prev['MACD'] >= prev['Signal_Line']: score -= 2
    else: score -= 1

    # Permanently triggers on ACCUMULATE (score >= 1) and STRONG BUY (score >= 3)
    if score >= 1:
        signal_label = "STRONG BUY" if score >= 3 else "ACCUMULATE"
        atr = float(latest['ATR']) if not np.isnan(latest['ATR']) else float(latest['Close']) * 0.03
        close_price = float(latest['Close'])
        return {
            "Ticker": ticker.replace(".CA", ""),
            "Company Name": ALL_STOCKS.get(ticker, ticker),
            "Price (EGP)": round(close_price, 2),
            "Signal": signal_label,
            "Stop Loss": round(close_price - (1.5 * atr), 2),
            "Target Price": round(close_price + (3.0 * atr), 2)
        }
    return None

def dispatch_institutional_email(buy_opportunities):
    if not SENDER_EMAIL or not APP_PASSWORD:
        print("SMTP credentials missing in GitHub Secrets. Skipping email dispatch.")
        return False

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
            <p style="margin: 0 0 20px 0; font-size: 12px; color: #6B7280; text-transform: uppercase; letter-spacing: 1px;">Automated Cloud Signal Notification</p>
            <p style="font-size: 14px; color: #374151; line-height: 1.5;">
                Scheduled quantitative screening has identified an actionable <strong>ACCUMULATE / STRONG BUY</strong> signal on the following monitored equities:
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
    return True

if __name__ == "__main__":
    watchlist = load_watchlist()
    already_sent_today = load_sent_log()
    tv_quotes = fetch_live_tv_quotes()
    new_opportunities = []

    for ticker in watchlist:
        clean_code = ticker.replace(".CA", "")
        if clean_code in already_sent_today:
            continue
        res = evaluate_equity(ticker, tv_quotes)
        if res is not None:
            new_opportunities.append(res)

    if new_opportunities:
        if dispatch_institutional_email(new_opportunities):
            for item in new_opportunities:
                already_sent_today.add(item["Ticker"])
            save_sent_log(already_sent_today)
            print(f"Dispatched alerts for: {[x['Ticker'] for x in new_opportunities]}")
    else:
        print("No new Accumulate or Strong Buy signals detected during this scan.")
