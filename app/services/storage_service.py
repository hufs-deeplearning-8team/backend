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
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION_NAME,
            config=Config(signature_version='s3v4')
        )
        self.bucket_name = settings.S3_DEPLOYMENT_BUCKET
    
    async def upload_file(self, file_content: bytes, s3_path: str) -> None:
        """단일 파일을 S3에 업로드"""
        try:
            self.s3_client.upload_fileobj(
                io.BytesIO(file_content), 
                self.bucket_name, 
                s3_path
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail=f"S3 파일 업로드 중 오류가 발생했습니다: {str(e)}"
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
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail=f"S3 파일 업로드 중 오류가 발생했습니다: {str(e)}"
            )
    
    async def download_file(self, s3_path: str) -> bytes:
        """S3에서 파일 다운로드"""
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_path)
            return response['Body'].read()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"S3 파일 다운로드 중 오류가 발생했습니다: {str(e)}"
            )
    
    async def delete_file(self, s3_path: str) -> None:
        """S3에서 파일 삭제"""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_path)
        except Exception as e:
            # 삭제 실패는 로그만 남기고 예외는 발생시키지 않음
            print(f"S3 파일 삭제 실패 (경고): {s3_path} - {str(e)}")
    
    async def delete_multiple_files(self, s3_paths: List[str]) -> None:
        """S3에서 여러 파일 삭제"""
        for path in s3_paths:
            await self.delete_file(path)
    
    async def cleanup_image_files(self, image_id: int, filename: str = None) -> None:
        """이미지 관련 모든 파일 정리"""
        paths_to_delete = self.get_image_paths(image_id, filename)
        await self.delete_multiple_files(paths_to_delete)
    
    def get_image_paths(self, image_id: int, filename: str = None) -> List[str]:
        """이미지 ID를 기반으로 S3 경로들 생성"""
        if filename:
            filename_without_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
            return [
                f"image/{image_id}/{filename_without_ext}_origi.png",
                f"image/{image_id}/{filename_without_ext}_wm.png"
            ]
        else:
            # 하위 호환성을 위해 기존 방식도 지원
            return [
                f"image/{image_id}/gt.png",
                f"image/{image_id}/sr_h.png"
            ]
    
    def get_record_path(self, validation_uuid: str, filename: str) -> str:
        """검증 레코드 S3 경로 생성"""
        return f"record/{validation_uuid}/{filename}"
    
    def get_image_urls(self, image_id: int, filename: str = None) -> dict:
        """이미지 URL들 생성"""
        if filename:
            filename_without_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
            return {
                "gt": f"{settings.s3_image_dir}/{image_id}/{filename_without_ext}_origi.png",
                "sr_h": f"{settings.s3_image_dir}/{image_id}/{filename_without_ext}_wm.png"
            }
        else:
            # 하위 호환성을 위해 기존 방식도 지원
            return {
                "gt": f"{settings.s3_image_dir}/{image_id}/gt.png",
                "sr_h": f"{settings.s3_image_dir}/{image_id}/sr_h.png"
            }
    
    async def test_s3_connection(self) -> bool:
        """S3 연결 테스트"""
        try:
            # 버킷 존재 확인
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            return True
        except Exception as e:
            print(f"S3 connection test failed: {str(e)}")
            return False
    
    async def test_upload(self) -> bool:
        """S3 업로드 테스트"""
        try:
            test_content = b"test file content"
            test_path = "test/test.txt"
            
            # 테스트 파일 업로드
            await self.upload_file(test_content, test_path)
            
            # 테스트 파일 삭제
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=test_path)
            return True
        except Exception as e:
            print(f"S3 upload test failed: {str(e)}")
            return False


storage_service = StorageService()