#!/bin/bash

# Start the new Docker container using deploy setup
echo "Starting Aegis backend application..."

# Change to deploy directory
cd /home/ubuntu/deploy

# Load environment variables from .env file
if [ -f ".env" ]; then
    echo "Loading environment variables from .env file"
    source .env
else
    echo "ERROR: .env file not found"
    exit 1
fi

# Debug: Print environment variables
echo "=== Environment Variables Debug ==="
echo "AWS_ACCOUNT_ID: $AWS_ACCOUNT_ID"
echo "ECR_REPOSITORY_NAME: $ECR_REPOSITORY_NAME"
echo "DB_HOST: $DB_HOST"
echo "ACCESS_TOKEN_EXPIRE_MINUTES: $ACCESS_TOKEN_EXPIRE_MINUTES"
echo "JWT_SECRET_KEY: ${JWT_SECRET_KEY:0:10}..." 
echo "==================================="

# Use environment variables from GitHub Secrets
export ECR_REPOSITORY_ID=${AWS_ACCOUNT_ID}
export ECR_REGION=${AWS_REGION}
export ECR_IMAGE_TAG=latest

# Set executable permissions for scripts
chmod +x ecr-login.sh

# ECR login
./ecr-login.sh

# Pull latest image from ECR
ECR_IMAGE_URL="$ECR_REPOSITORY_ID.dkr.ecr.$ECR_REGION.amazonaws.com/$ECR_REPOSITORY_NAME:$ECR_IMAGE_TAG"
echo "Pulling image: $ECR_IMAGE_URL"
docker pull $ECR_IMAGE_URL

# Force remove old containers and images
docker compose --profile app down --rmi all 2>/dev/null || true

# Start application with docker-compose
echo "Starting docker-compose services..."
docker compose --profile app up -d

# Wait a moment and check status
sleep 10
echo "=== Container status after startup ==="
docker ps -a

# Show logs if containers failed to start
if ! docker ps | grep -q aegis-backend; then
    echo "=== Backend container logs ==="
    docker compose --profile app logs backend
fi

if ! docker ps | grep -q aegis-nginx; then
    echo "=== Nginx container logs ==="
    docker compose --profile app logs nginx
fi

echo "Application startup completed"