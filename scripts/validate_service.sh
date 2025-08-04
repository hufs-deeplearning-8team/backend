#!/bin/bash

# Validate that the service is running correctly
echo "Validating Aegis backend service..."

# Wait for the service to start
sleep 30

# Check if backend container is running
if ! docker ps | grep -q aegis-backend; then
    echo "ERROR: Backend container is not running"
    echo "=== Docker container status ==="
    docker ps -a
    echo "=== Docker compose logs ==="
    cd /home/ubuntu/deploy && docker compose --profile app logs --tail=50
    exit 1
fi

# Check if nginx container is running
if ! docker ps | grep -q aegis-nginx; then
    echo "ERROR: Nginx container is not running"
    exit 1
fi

echo "Service validation completed successfully"