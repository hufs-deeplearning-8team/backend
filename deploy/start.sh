#!/bin/bash

# .env 파일에서 환경변수 로드
source .env

# 기존 컨테이너 정리
sudo docker compose down

# ECR 로그인
./ecr-login.sh

# ECR에서 최신 이미지 pull
ECR_IMAGE_URL="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION_NAME.amazonaws.com/$ECR_REPOSITORY_NAME:$ECR_IMAGE_TAG"
echo "Pulling image: $ECR_IMAGE_URL"
sudo docker pull $ECR_IMAGE_URL

# SSL 인증서 발급 (최초 1회 또는 필요시)
sudo docker compose --profile ssl-init up

# 앱 실행
sudo docker compose --profile app up -d
