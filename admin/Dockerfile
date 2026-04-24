FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir fastapi==0.115.0 httpx==0.27.2 uvicorn==0.32.0 psycopg2-binary==2.9.9
COPY app.py /app/
COPY static /app/static/
ENV PYTHONUNBUFFERED=1
EXPOSE 4001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "4001"]
