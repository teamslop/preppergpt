FROM python:3.12-slim
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        grim \
        imagemagick \
        scrot \
        wmctrl \
        x11-utils \
        xdg-utils \
        xdotool \
        xterm \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir playwright==1.58.0
COPY app.py /app/app.py
ENV PYTHONUNBUFFERED=1
CMD ["python", "/app/app.py"]
