
def check_risk(stock_code: str, daily_change: float, threshold: float = 5.0):
    """
    daily_change: 当日涨跌幅，单位为百分比。
    例如 -5.8 表示下跌 5.8%。
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


if __name__ == "__main__":
    print(check_risk("NVDA", -5.8, 5.0))
    print(check_risk("AAPL", -2.0, 5.0))
