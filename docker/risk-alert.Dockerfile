FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    SEND_DISCORD=false
RUN groupadd -r app && useradd -r -g app app \
    && mkdir -p /app/.state /app/artifacts \
    && chown -R app:app /app
RUN pip install --no-cache-dir 'yfinance>=0.2.60,<1.0'
COPY --chown=app:app src/risk_alert.py src/alert_state.py src/observability.py /app/src/
USER app
CMD ["python", "-m", "src.risk_alert"]
