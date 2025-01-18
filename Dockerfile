# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install required system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    avrdude \
    wget \
    unzip \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install arduino-cli
RUN wget https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Linux_ARM64.tar.gz && \
    tar -xvf arduino-cli_latest_Linux_ARM64.tar.gz && \
    mv arduino-cli /usr/local/bin/ && \
    chmod +x /usr/local/bin/arduino-cli && \
    rm arduino-cli_latest_Linux_ARM64.tar.gz

# Initialize arduino-cli and install cores
RUN arduino-cli config init && \
    arduino-cli core update-index && \
    arduino-cli core install arduino:avr && \
    arduino-cli core install esp32:esp32

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port the app runs on
EXPOSE 8080

# Define environment variable
ENV FLASK_ENV=development

# Run the command to start the app
CMD ["python", "app.py"]