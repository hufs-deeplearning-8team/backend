#!/bin/bash

# Start the new Docker container using deploy setup
echo "Starting Aegis backend application..."

# Change to deploy directory
cd /home/ubuntu/deploy

# Load environment variables from .env file
if [ -f ".env" ]; then
    echo "Loading environment variables from .env file"
    echo "=== .env file contents ==="
    cat .env
    echo "=========================="
    set -a  # automatically export all variables
    source .env
    set +a
    echo "=== Environment check after loading .env ==="
    echo "AWS_ACCESS_KEY_ID is set: ${AWS_ACCESS_KEY_ID:+YES}"
    echo "AWS_SECRET_ACCESS_KEY is set: ${AWS_SECRET_ACCESS_KEY:+YES}"
    echo "=========================="
else
    echo "ERROR: .env file not found"
    exit 1
fi

# Debug: Print environment variables
echo "=== Environment Variables Debug ==="
echo "AWS_ACCOUNT_ID: $AWS_ACCOUNT_ID"
echo "ECR_REPOSITORY_NAME: $ECR_REPOSITORY_NAME"
echo "AWS_ACCOUNT_ID: $AWS_ACCOUNT_ID"
echo "AWS_REGION_NAME: $AWS_REGION_NAME"
echo "ECR_IMAGE_TAG: $ECR_IMAGE_TAG"
echo "DB_HOST: $DB_HOST"
echo "S3_DEPLOYMENT_BUCKET: $S3_DEPLOYMENT_BUCKET"
echo "AWS_REGION_NAME: $AWS_REGION_NAME"
echo "AWS_REGION: $AWS_REGION"
echo "ACCESS_TOKEN_EXPIRE_MINUTES: $ACCESS_TOKEN_EXPIRE_MINUTES"
echo "JWT_SECRET_KEY: ${JWT_SECRET_KEY:0:10}..." 
echo "SMTP_HOST: $SMTP_HOST"
echo "SMTP_PORT: $SMTP_PORT"
echo "SMTP_USER: $SMTP_USER"
echo "SMTP_PASSWORD: ${SMTP_PASSWORD:0:5}..."
echo "EMAIL_FROM: $EMAIL_FROM"
echo "EMAIL_FROM_NAME: $EMAIL_FROM_NAME"
echo "==================================="

# Use environment variables from GitHub Secrets
export ECR_IMAGE_TAG=${ECR_IMAGE_TAG:-latest}

echo "=== Final export values ==="
echo "AWS_ACCOUNT_ID: $AWS_ACCOUNT_ID"
echo "AWS_REGION_NAME: $AWS_REGION_NAME"  
echo "ECR_IMAGE_TAG: $ECR_IMAGE_TAG"
echo "=========================="

# Set executable permissions for scripts
chmod +x ecr-login.sh

# ECR login
./ecr-login.sh

# Pull latest image from ECR
ECR_IMAGE_URL="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION_NAME.amazonaws.com/$ECR_REPOSITORY_NAME:$ECR_IMAGE_TAG"
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
    docker compose --profile app logs backend --tail=100
    echo "=== All containers status ==="
    docker compose --profile app ps -a
    echo "=== Image pull check ==="
    docker images | grep "$ECR_REPOSITORY_NAME" || echo "No images found for $ECR_REPOSITORY_NAME"
else
    echo "=== Backend container environment check ==="
    docker exec aegis-backend printenv | grep -E "(S3_DEPLOYMENT_BUCKET|AWS_REGION_NAME|SMTP_HOST|EMAIL_FROM)" || echo "Environment variables not found in container"
fi

if ! docker ps | grep -q aegis-nginx; then
    echo "=== Nginx container logs ==="
    docker compose --profile app logs nginx --tail=50
fi

echo "Application startup completed"