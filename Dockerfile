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
    && rm -rf /var/lib/apt/lists/*

# Install arduino-cli
RUN wget https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Linux_64bit.tar.gz && \
    tar -xvf arduino-cli_latest_Linux_64bit.tar.gz && \
    mv arduino-cli /usr/local/bin/ && \
    rm arduino-cli_latest_Linux_64bit.tar.gz

# Initialize arduino-cli
RUN arduino-cli config init && \
    arduino-cli core update-index && \
    arduino-cli core install arduino:avr

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port the app runs on
EXPOSE 8080

# Define environment variable
ENV FLASK_ENV=development

# Run the command to start the app
CMD ["python", "app.py"]