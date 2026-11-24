FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --retries=20 --start-period=600s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

# Migrate; on an empty database load prices + demo account before serving. Otherwise serve the
# stored prices immediately and refresh them from the provider in the background.
CMD ["sh", "-c", "alembic upgrade head && python -m scripts.seed --if-empty && (python -m scripts.seed &) && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
