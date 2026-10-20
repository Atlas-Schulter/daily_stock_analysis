
import os
import math


def check_risk(
    stock_code: str,
    daily_change: float,
    threshold: float = 5.0
):
    """Check whether a stock decline triggers an alert."""
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
    """Check risk using a normalized market quote."""
    stock_code = quote["code"]
    daily_change = float(quote["change_pct"])

    return check_risk(stock_code, daily_change, threshold)


def get_stock_quote(stock_code: str):
    """Fetch the latest two available daily closes."""
    import yfinance as yf

    ticker = yf.Ticker(stock_code)
    history = ticker.history(
        period="1mo",
        interval="1d",
        auto_adjust=True
    )

    if history.empty:
        raise ValueError(f"No market data for {stock_code}")

    closes = history["Close"].dropna()

    if len(closes) < 2:
        raise ValueError(f"Insufficient data for {stock_code}")

    previous_close = float(closes.iloc[-2])
    latest_close = float(closes.iloc[-1])

    if previous_close <= 0:
        raise ValueError("Invalid previous close price")

    daily_change = (
        (latest_close - previous_close)
        / previous_close
        * 100
    )

    return {
        "code": stock_code,
        "price": latest_close,
        "change_pct": daily_change,
        "date": str(closes.index[-1].date())
    }


def main():
    threshold = float(
        os.getenv("RISK_DROP_THRESHOLD", "5.0")
    )

    stock_codes = [
        code.strip().upper()
        for code in os.getenv(
            "STOCK_CODES", "NVDA,AAPL,TSLA"
        ).split(",")
        if code.strip()
    ]

    print("Starting real-time stock risk analysis...")
    print(f"Risk threshold: -{threshold}%")

    failed = []

    for stock_code in stock_codes:
        try:
            quote = get_stock_quote(stock_code)

            print(
                f"\nStock: {quote['code']}\n"
                f"Data Date: {quote['date']}\n"
                f"Latest Close: ${quote['price']:.2f}\n"
                f"Daily Change: {quote['change_pct']:.2f}%"
            )

            alert = check_risk_from_quote(
                quote, threshold
            )

            if alert:
                print(alert)
            else:
                print("No risk alert triggered.")

        except Exception as error:
            failed.append(stock_code)
            print(f"Error fetching {stock_code}: {error}")

    if failed:
        raise RuntimeError(
            "Failed to analyze: " + ", ".join(failed)
        )


if __name__ == "__main__":
    main()
