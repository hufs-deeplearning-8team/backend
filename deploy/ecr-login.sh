#!/bin/bash

# ECR 로그인 스크립트
echo "Logging into ECR..."

# Use environment variables from GitHub Secrets

# AWS 환경변수가 설정되어 있는지 확인
if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "ERROR: AWS credentials not set in environment"
    exit 1
fi

# ECR 로그인
aws ecr get-login-password --region $AWS_REGION_NAME | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION_NAME.amazonaws.com

if [ $? -eq 0 ]; then
    echo "Successfully logged into ECR"
else
    echo "ERROR: Failed to login to ECR"
    exit 1
fi