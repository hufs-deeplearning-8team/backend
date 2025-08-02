import io
from typing import List

import boto3
from botocore.client import Config
from fastapi import HTTPException, status

from app.config import settings


class StorageService:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            endpoint_url=settings.AWS_S3_ENDPOINT,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            config=Config(
                signature_version='s3v4',
                s3={
                    'addressing_style': 'path',
                    'use_ssl': True,
                    'verify': False
                }
            ),
            region_name=settings.AWS_REGION_NAME,
            use_ssl=True,
            verify=False
        )
        self.bucket_name = settings.BUCKET_NAME
    
    async def upload_file(self, file_content: bytes, s3_path: str) -> None:
        """단일 파일을 S3에 업로드"""
        try:
            self.s3_client.upload_fileobj(
                io.BytesIO(file_content), 
                self.bucket_name, 
                s3_path
            )
        except Exception as e:
            if "XMinioStorageFull" in str(e) or "Storage backend has reached its minimum free drive threshold" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_507_INSUFFICIENT_STORAGE, 
                    detail="저장 공간이 부족합니다. 관리자에게 문의하세요"
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail=f"파일 업로드 중 오류가 발생했습니다: {str(e)}"
            )
    
    async def upload_multiple_files(self, file_content: bytes, s3_paths: List[str]) -> None:
        """여러 파일을 S3에 업로드 (동일한 내용으로)"""
        try:
            for path in s3_paths:
                self.s3_client.upload_fileobj(
                    io.BytesIO(file_content), 
                    self.bucket_name, 
                    path
                )
        except Exception as e:
            if "XMinioStorageFull" in str(e) or "Storage backend has reached its minimum free drive threshold" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_507_INSUFFICIENT_STORAGE, 
                    detail="저장 공간이 부족합니다. 관리자에게 문의하세요"
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail=f"파일 업로드 중 오류가 발생했습니다: {str(e)}"
            )
    
    def get_image_paths(self, image_id: int) -> List[str]:
        """이미지 ID를 기반으로 S3 경로들 생성"""
        return [
            f"image/{image_id}/gt.png",
            f"image/{image_id}/lr.png", 
            f"image/{image_id}/sr.png",
            f"image/{image_id}/sr_h.png"
        ]
    
    def get_record_path(self, validation_uuid: str, filename: str) -> str:
        """검증 레코드 S3 경로 생성"""
        return f"record/{validation_uuid}/{filename}"
    
    def get_image_urls(self, image_id: int) -> dict:
        """이미지 URL들 생성"""
        return {
            "gt": f"{settings.s3_image_dir}/{image_id}/gt.png",
            "lr": f"{settings.s3_image_dir}/{image_id}/lr.png",
            "sr": f"{settings.s3_image_dir}/{image_id}/sr.png",
            "sr_h": f"{settings.s3_image_dir}/{image_id}/sr_h.png"
        }


storage_service = StorageService()