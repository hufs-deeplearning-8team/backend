#!/bin/bash

# Stop the running Docker containers using deploy setup
echo "Stopping existing Aegis backend application..."

# Stop any running containers with aegis names
docker stop aegis-backend aegis-nginx aegis-certbot-renew 2>/dev/null || true
docker rm aegis-backend aegis-nginx aegis-certbot-renew 2>/dev/null || true

# Stop containers using docker-compose if deploy directory exists
if [ -d "/home/ubuntu/deploy" ]; then
  cd /home/ubuntu/deploy
  docker compose --profile app down 2>/dev/null || true
fi

# Clean up old deploy directory for fresh deployment
sudo rm -rf /home/ubuntu/deploy 2>/dev/null || true
sudo mkdir -p /home/ubuntu/deploy
sudo chown ubuntu:ubuntu /home/ubuntu/deploy

# Clean up unused images
docker image prune -f

echo "Application stopped successfully"