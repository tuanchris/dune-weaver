#!/bin/bash
# Script to shutdown the host system from inside Docker container
# This must be placed on the host and mounted into the container

echo "$(date): Shutdown requested from Dune Weaver" >> /tmp/dune-weaver-shutdown.log

# Stop Docker containers gracefully
docker compose -f /app/docker-compose.yml down 2>/dev/null || true

# Shutdown the host system
shutdown -h now
