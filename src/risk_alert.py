
import os


def check_risk(
    stock_code: str,
    daily_change: float,
    threshold: float = 5.0
):
    """
    Check whether a stock's daily loss exceeds the threshold.

    daily_change: Daily percentage change.
    Example: -5.8 means a 5.8% decline.
    """
    if threshold <= 0:
        raise ValueError("threshold must be positive")

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
    """
    Check stock risk using a market quote dictionary.

    Expected format:
    {
        "code": "NVDA",
        "change_pct": -5.8
    }
    """
    stock_code = quote["code"]
    daily_change = float(quote["change_pct"])

    return check_risk(
        stock_code,
        daily_change,
        threshold
    )


def main():
    # Configurable risk threshold
    threshold = float(
        os.getenv("RISK_DROP_THRESHOLD", "5.0")
    )

    # Sample market data for testing
    # TODO: Replace with actual market data
    quotes = [
        {"code": "NVDA", "change_pct": -5.8},
        {"code": "AAPL", "change_pct": -2.0},
        {"code": "TSLA", "change_pct": -5.0}
    ]

    print("Starting stock risk analysis...")

    for quote in quotes:
        alert = check_risk_from_quote(
            quote,
            threshold
        )

        if alert:
            print(alert)
            print("-" * 40)
        else:
            print(
                f"{quote['code']}: "
                f"No risk alert triggered."
            )


if __name__ == "__main__":
    main()
