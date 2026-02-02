# Backend-only Dockerfile
FROM python:3.11-slim-bookworm

# Faster, repeatable builds
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ make libjpeg-dev zlib1g-dev git \
        # GPIO/NeoPixel support for DW LEDs
        python3-dev python3-pip \
        libgpiod2 libgpiod-dev \
        scons \
        systemd \
        # Docker CLI for container self-restart/update
        ca-certificates curl gnupg \
    && pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    # Install Docker CLI from official Docker repo
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && apt-get purge -y gcc g++ make scons \
    && rm -rf /var/lib/apt/lists/*

# Copy backend code
COPY . .

# Expose backend API port
EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
