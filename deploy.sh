#!/bin/bash

# 배포 스크립트 - 원격 서버에서 실행
# 새로운 Docker 이미지가 푸시되면 서비스를 재시작합니다.

set -e  # 에러 발생시 스크립트 중단

DOCKER_IMAGE="daehyuh/aegis-backend:latest"
COMPOSE_FILE="docker-compose.yml"
SERVICE_NAME="backend"

echo "🚀 Starting deployment process..."

# 1. 최신 이미지 pull
echo "📥 Pulling latest Docker image..."
docker pull $DOCKER_IMAGE

# 2. 현재 실행 중인 컨테이너 확인
if docker-compose ps | grep -q $SERVICE_NAME; then
    echo "🔄 Stopping current service..."
    docker-compose stop $SERVICE_NAME
fi

# 3. 새 컨테이너로 서비스 시작
echo "🔧 Starting service with new image..."
docker-compose up -d $SERVICE_NAME

# 5. 사용하지 않는 이미지 정리
echo "🧹 Cleaning up unused images..."
docker image prune -f

echo "🎉 Deployment completed!"