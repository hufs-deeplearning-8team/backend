import io
import os
import logging
from typing import List

import boto3
from botocore.client import Config
from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self):
        self.bucket_name = settings.S3_DEPLOYMENT_BUCKET
        self.is_mock = False
        self.s3_client = None
        self.image_base_url = ""
        self.record_base_url = ""
        self._local_root = os.path.abspath(os.getcwd())
        self._local_image_dir: str | None = None
        self._local_record_dir: str | None = None
        self._ensure_local_root()

        mandatory_values = {
            "AWS_ACCESS_KEY_ID": settings.AWS_ACCESS_KEY_ID,
            "AWS_SECRET_ACCESS_KEY": settings.AWS_SECRET_ACCESS_KEY,
            "AWS_REGION_NAME": settings.AWS_REGION_NAME,
            "S3_DEPLOYMENT_BUCKET": self.bucket_name,
        }

        missing = [key for key, value in mandatory_values.items() if value in (None, "")]
        if missing:
            if settings.IS_PRODUCTION:
                raise RuntimeError(
                    "S3 사용을 위해 필요한 설정이 누락되었습니다. "
                    f"확인 필요한 값: {', '.join(missing)}"
                )
            logger.warning(
                "S3 설정이 누락되어 로컬 파일 시스템을 사용합니다. missing=%s", missing
            )
            self._enable_mock_storage()
            return

        try:
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION_NAME,
                config=Config(signature_version="s3v4"),
            )
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            self.image_base_url = settings.s3_image_dir
            self.record_base_url = settings.s3_record_dir
        except Exception as exc:
            if settings.IS_PRODUCTION:
                logger.error("S3 초기화 실패: %s", exc)
                raise RuntimeError(
                    "S3 초기화 중 오류가 발생했습니다. IAM 권한과 버킷 설정을 확인해 주세요."
                ) from exc
            logger.warning(
                "S3 초기화 실패로 로컬 파일 시스템을 사용합니다. error=%s", exc
            )
            self._enable_mock_storage()

    async def upload_file(self, file_content: bytes, s3_path: str) -> None:
        """단일 파일을 S3에 업로드"""
        try:
            if self.is_mock:
                local_path = self._resolve_local_path(s3_path)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, "wb") as file:
                    file.write(file_content)
                return

            self.s3_client.upload_fileobj(
                io.BytesIO(file_content),
                self.bucket_name,
                s3_path,
            )
        except Exception as e:
            logger.error("S3 업로드 실패 (%s): %s", s3_path, e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"S3 파일 업로드 중 오류가 발생했습니다: {str(e)}"
            ) from e

    async def upload_multiple_files(self, file_content: bytes, s3_paths: List[str]) -> None:
        """여러 파일을 S3에 업로드 (동일한 내용으로)"""
        try:
            for path in s3_paths:
                if self.is_mock:
                    local_path = self._resolve_local_path(path)
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    with open(local_path, "wb") as file:
                        file.write(file_content)
                    continue

                self.s3_client.upload_fileobj(
                    io.BytesIO(file_content),
                    self.bucket_name,
                    path,
                )
        except Exception as e:
            logger.error("S3 다중 업로드 실패: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"S3 파일 업로드 중 오류가 발생했습니다: {str(e)}"
            ) from e

    async def download_file(self, s3_path: str) -> bytes:
        """S3에서 파일 다운로드"""
        try:
            if self.is_mock:
                local_path = self._resolve_local_path(s3_path)
                with open(local_path, "rb") as file:
                    return file.read()

            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_path)
            return response["Body"].read()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"S3 파일 다운로드 중 오류가 발생했습니다: {str(e)}"
            ) from e

    async def delete_file(self, s3_path: str) -> None:
        """S3에서 파일 삭제"""
        try:
            if self.is_mock:
                local_path = self._resolve_local_path(s3_path)
                if os.path.exists(local_path):
                    os.remove(local_path)
                return

            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_path)
        except Exception as e:
            logger.warning("S3 파일 삭제 실패 (%s): %s", s3_path, e)

    async def delete_multiple_files(self, s3_paths: List[str]) -> None:
        """S3에서 여러 파일 삭제"""
        for path in s3_paths:
            await self.delete_file(path)

    async def cleanup_image_files(self, image_id: int, filename: str | None = None) -> None:
        """이미지 관련 모든 파일 정리"""
        paths_to_delete = self.get_image_paths(image_id, filename)
        await self.delete_multiple_files(paths_to_delete)

    def get_image_paths(self, image_id: int, filename: str | None = None) -> List[str]:
        """이미지 ID를 기반으로 S3 경로들 생성"""
        if filename:
            filename_without_ext = filename.rsplit(".", 1)[0] if "." in filename else filename
            return [
                f"image/{image_id}/{filename_without_ext}_origi.png",
                f"image/{image_id}/{filename_without_ext}_wm.png",
            ]
        return [
            f"image/{image_id}/gt.png",
            f"image/{image_id}/sr_h.png",
        ]

    def get_record_path(self, validation_uuid: str, filename: str) -> str:
        """검증 레코드 S3 경로 생성"""
        return f"record/{validation_uuid}/{filename}"

    def get_image_urls(self, image_id: int, filename: str | None = None) -> dict:
        """이미지 URL들 생성"""
        if filename:
            filename_without_ext = filename.rsplit(".", 1)[0] if "." in filename else filename
            return {
                "gt": self._build_url(image_id, f"{filename_without_ext}_origi.png"),
                "sr_h": self._build_url(image_id, f"{filename_without_ext}_wm.png"),
            }
        return {
            "gt": self._build_url(image_id, "gt.png"),
            "sr_h": self._build_url(image_id, "sr_h.png"),
        }

    async def test_s3_connection(self) -> bool:
        """S3 연결 테스트"""
        try:
            if self.is_mock:
                return True

            self.s3_client.head_bucket(Bucket=self.bucket_name)
            return True
        except Exception as e:
            logger.error("S3 connection test failed: %s", e)
            return False

    async def test_upload(self) -> bool:
        """S3 업로드 테스트"""
        test_content = b"test file content"
        test_path = "test/test.txt"
        try:
            await self.upload_file(test_content, test_path)
            if self.is_mock:
                local_path = self._resolve_local_path(test_path)
                if os.path.exists(local_path):
                    os.remove(local_path)
                return True

            self.s3_client.delete_object(Bucket=self.bucket_name, Key=test_path)
            return True
        except Exception as e:
            logger.error("S3 upload test failed: %s", e)
            return False

    def _ensure_local_root(self) -> None:
        """로컬 저장소 루트 생성"""
        os.makedirs(self._local_root, exist_ok=True)

    def _enable_mock_storage(self) -> None:
        """S3 대신 로컬 파일 시스템을 사용하도록 설정"""
        self.is_mock = True
        self.bucket_name = "local-mock-bucket"
        local_image_dir = os.path.join(self._local_root, settings.IMAGEDIR or "image")
        local_record_dir = os.path.join(self._local_root, settings.RECORDDIR or "record")
        os.makedirs(local_image_dir, exist_ok=True)
        os.makedirs(local_record_dir, exist_ok=True)

        self.image_base_url = "/image"
        self.record_base_url = "/record"
        self._local_image_dir = local_image_dir
        self._local_record_dir = local_record_dir

    def _resolve_local_path(self, s3_path: str) -> str:
        """S3 경로를 로컬 파일 시스템 경로로 변환"""
        normalized_path = os.path.normpath(os.path.join(self._local_root, s3_path))
        if not normalized_path.startswith(os.path.abspath(self._local_root) + os.sep):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="잘못된 파일 경로입니다."
            )
        return normalized_path

    def _build_url(self, image_id: int, filename: str) -> str:
        """mock 여부에 따른 URL 또는 경로를 생성"""
        if self.is_mock:
            return f"{self.image_base_url}/{image_id}/{filename}"
        return f"{self.image_base_url}/{image_id}/{filename}"

    def build_record_url(self, validation_uuid: str, filename: str) -> str:
        """검증 결과 파일에 대한 URL 생성"""
        if self.is_mock:
            return f"{self.record_base_url}/{validation_uuid}/{filename}"
        return f"{self.record_base_url}/{validation_uuid}/{filename}"

    @property
    def local_root(self) -> str:
        """mock 저장소의 루트 디렉터리"""
        return self._local_root
    
    @property
    def local_image_dir(self) -> str:
        """mock 이미지 디렉터리"""
        return self._local_image_dir or os.path.join(self._local_root, settings.IMAGEDIR or "image")
    
    @property
    def local_record_dir(self) -> str:
        """mock 검증 결과 디렉터리"""
        return self._local_record_dir or os.path.join(self._local_root, settings.RECORDDIR or "record")

    def resolve_local_file(self, relative_path: str) -> str:
        """mock 저장소 내 파일의 절대 경로 반환"""
        return self._resolve_local_path(relative_path)


storage_service = StorageService()
