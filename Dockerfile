FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Metric-compatible Arial substitute for PDF export — without it reportlab
# falls back to Helvetica and the output drifts from local rendering.
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

EXPOSE 8000

CMD python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
