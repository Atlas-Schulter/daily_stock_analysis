
import math
import os
import json
import urllib.request
import urllib.error


def check_risk(
    stock_code: str,
    daily_change: float,
    threshold: float = 5.0
):
    """Return an alert if the daily loss reaches the threshold."""
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("threshold must be positive and finite")

    if not math.isfinite(daily_change):
        raise ValueError("daily_change must be finite")

    if daily_change <= -threshold:
        return (
            f"⚠️ Stock Risk Alert\n"
            f"Stock: {stock_code}\n"
            f"Daily Change: {daily_change:.2f}%\n"
            f"Threshold: -{threshold:.2f}%"
        )

    return None


def check_risk_from_quote(
    quote: dict,
    threshold: float = 5.0
):
    """Evaluate risk using a normalized market quote."""
    return check_risk(
        quote["code"],
        float(quote["change_pct"]),
        threshold
    )


def get_stock_quote(stock_code: str):
    """Retrieve the latest two available daily closing prices."""
    import yfinance as yf

    history = yf.Ticker(stock_code).history(
        period="1mo",
        interval="1d",
        auto_adjust=True
    )

    if history.empty:
        raise ValueError(f"No market data for {stock_code}")

    closes = history["Close"].dropna()

    if len(closes) < 2:
        raise ValueError(f"Insufficient data for {stock_code}")

    previous = float(closes.iloc[-2])
    latest = float(closes.iloc[-1])

    if not math.isfinite(previous) or previous <= 0:
        raise ValueError("Invalid previous close")
    if not math.isfinite(latest):
        raise ValueError("Invalid latest close")

    change_pct = (latest - previous) / previous * 100

    return {
        "code": stock_code,
        "price": latest,
        "change_pct": change_pct,
        "date": str(closes.index[-1].date())
    }


def send_discord(message: str):
    """Send a message through the configured Discord webhook."""
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

    if not webhook_url:
        raise ValueError("DISCORD_WEBHOOK_URL is not configured")

    payload = json.dumps({
        "content": message
    }).encode("utf-8")

    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "StockRiskAlert/1.0"
        },
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status not in (200, 204):
            raise RuntimeError(
                f"Discord returned HTTP {response.status}"
            )


def main():
    threshold = float(os.getenv("RISK_DROP_THRESHOLD", "5.0"))

    stock_codes = [
        code.strip().upper()
        for code in os.getenv(
            "STOCK_CODES", "NVDA,AAPL,TSLA"
        ).split(",")
        if code.strip()
    ]

    send_enabled = os.getenv(
        "SEND_DISCORD", "false"
    ).lower() == "true"

    webhook_test = os.getenv(
        "WEBHOOK_TEST", "false"
    ).lower() == "true"

    # Explicit connection test; no stock data required.
    if webhook_test:
        if not send_enabled:
            raise ValueError("WEBHOOK_TEST requires SEND_DISCORD=true")

        send_discord(
            "✅ Stock Risk Alert: Discord connection test successful."
        )
        print("Discord connection test successful.")
        return

    print("Starting stock risk analysis...")
    print(f"Risk threshold: -{threshold}%")
    print(f"Discord notifications enabled: {send_enabled}")

    failed = []
    alerts = []

    for stock_code in stock_codes:
        try:
            quote = get_stock_quote(stock_code)

            print(
                f"\nStock: {quote['code']}\n"
                f"Data Date: {quote['date']}\n"
                f"Latest Close: {quote['price']:.2f}\n"
                f"Daily Change: {quote['change_pct']:.2f}%"
            )

            alert = check_risk_from_quote(quote, threshold)

            if alert:
                print(alert)
                alerts.append(alert)
            else:
                print("No risk alert triggered.")

        except Exception as error:
            failed.append(stock_code)
            print(f"Error analyzing {stock_code}: {error}")

    if alerts and send_enabled:
        message = "\n\n".join(alerts)
        send_discord(message[:2000])
        print("Discord risk alert sent successfully.")
    elif alerts:
        print("Risk alerts detected; Discord sending disabled.")

    if failed:
        raise RuntimeError(
            "Failed to analyze: " + ", ".join(failed)
        )


if __name__ == "__main__":
    main()
