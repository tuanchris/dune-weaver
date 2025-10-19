FROM --platform=$TARGETPLATFORM python:3.11-slim-bookworm

# Faster, repeatable builds
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libjpeg-dev zlib1g-dev git \
        # GPIO/NeoPixel support for DW LEDs
        python3-dev python3-pip \
        libgpiod2 libgpiod-dev \
    && pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y gcc \
    && rm -rf /var/lib/apt/lists/*

COPY . .

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
