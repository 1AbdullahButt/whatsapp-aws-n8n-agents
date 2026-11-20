# One small Python image for both local services:
#   api              extractor API (port 8101)   - default command below
#   mock-accounting  MOCK accounting API (8102)  - command set in docker-compose.yml
FROM python:3.12.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# `shared` lives one folder up (D:\Project\Portfolio\shared). docker-compose.yml
# passes it in as an extra build context called "shared".
COPY --from=shared . /app/shared
COPY extractor /app/extractor
COPY mock_accounting /app/mock_accounting

ENV INBOX_DIR=/app/inbox \
    DATA_DIR=/app/data \
    OUTBOX_DIR=/app/outbox \
    PYTHONUNBUFFERED=1

EXPOSE 8101
CMD ["python", "-m", "uvicorn", "extractor.api:app", "--host", "0.0.0.0", "--port", "8101"]
