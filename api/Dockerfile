FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install . && useradd --create-home --uid 10001 app

USER app
EXPOSE 8000
# The API is only reachable through nginx, so the client IP nginx forwards can be trusted
# (rate limits are per client IP). Don't publish port 8000 directly with this setting.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
