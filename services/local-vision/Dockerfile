FROM python:3.12-slim

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pillow requests transformers accelerate torch rapidocr-onnxruntime
COPY app.py /app/app.py

ENV PYTHONUNBUFFERED=1
CMD ["python", "/app/app.py"]
