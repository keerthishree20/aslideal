# AsliDeal, ready to host. With no SERPAPI_KEY set it serves the recorded
# responses in fixtures/cache, so a hosted copy costs nothing and leaks no key.
FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY fixtures/ fixtures/

ENV DEMO_MODE=1 PORT=8000
EXPOSE 8000
WORKDIR /app/backend
CMD ["sh", "-c", "uvicorn aslideal.api:app --host 0.0.0.0 --port ${PORT}"]
