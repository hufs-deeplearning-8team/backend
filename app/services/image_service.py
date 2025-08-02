import logging
from typing import List, Dict, Any

from fastapi import HTTPException, status, UploadFile
import sqlalchemy

from app.config import settings
from app.db import database
from app.models import Image
from app.schemas import BaseResponse
from app.services.auth_service import auth_service
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)


class ImageService:
    def __init__(self):
        self.auth_service = auth_service
        self.storage_service = storage_service
    
    def validate_file(self, file: UploadFile) -> None:
        """파일 유효성 검증"""
        if not file:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="파일이 필요합니다"
            )
        
        if not file.filename or not file.filename.endswith(".png"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="PNG 형식만 지원합니다"
            )
        
        if file.content_type != "image/png":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="PNG 형식만 지원합니다"
            )
        
        if file.size and file.size > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, 
                detail=f"파일 크기가 {settings.MAX_FILE_SIZE_MB}MB를 초과합니다"
            )
    
    def clean_filename(self, filename: str) -> str:
        """파일명에서 "protected_" prefix 제거"""
        if filename and filename.startswith("protected_"):
            return filename[10:]  # "protected_" 길이만큼 제거
        return filename
    
    async def upload_image(self, file: UploadFile, copyright: str, access_token: str) -> BaseResponse:
        """이미지 업로드 처리"""
        user_id = self.auth_service.get_user_id_from_token(access_token)
        self.validate_file(file)
        
        # 파일명 정리
        original_filename = self.clean_filename(file.filename)
        logger.info(f"Original filename: {file.filename} -> Cleaned: {original_filename}")
        
        # DB에 이미지 정보 저장
        query = (
            sqlalchemy.insert(Image)
            .values(
                user_id=int(user_id), 
                copyright=copyright, 
                filename=original_filename
            )
            .returning(Image)
        )
        
        result = await database.fetch_one(query)
        inserted_data = dict(result)
        image_id = inserted_data["id"]


        ## AI에 이미지 전송하고 받아오기
        
        
        # 파일 내용 읽기
        contents = await file.read()
        
        # S3에 다중 경로로 업로드
        s3_paths = self.storage_service.get_image_paths(image_id)
        await self.storage_service.upload_multiple_files(contents, s3_paths)
        
        return BaseResponse(
            success=True, 
            description="생성 성공", 
            data=[inserted_data]
        )
    
    async def get_user_images(self, access_token: str, limit: int = 20, offset: int = 0) -> BaseResponse:
        """사용자가 업로드한 이미지 목록 조회"""
        user_id = self.auth_service.get_user_id_from_token(access_token)
        
        logger.info(f"User {user_id} requested their uploaded images (limit={limit}, offset={offset})")
        
        

        try:
            # 사용자가 업로드한 이미지 목록 조회
            query = (
                Image.__table__.select()
                .where(Image.user_id == int(user_id))
                .order_by(Image.time_created.desc())
                .limit(limit)
                .offset(offset)
            )
            
            images = await database.fetch_all(query)
            
            # 응답 데이터 구성
            image_list = []
            for image in images:
                image_data = {
                    "image_id": image["id"],
                    "filename": image["filename"],
                    "copyright": image["copyright"],
                    "upload_time": image["time_created"].isoformat(),
                    "s3_paths": self.storage_service.get_image_urls(image["id"])
                }
                image_list.append(image_data)
            
            logger.info(f"Retrieved {len(image_list)} images for user {user_id}")
            
            return BaseResponse(
                success=True,
                description=f"{len(image_list)}개의 업로드된 이미지를 조회했습니다.",
                data=image_list
            )
            
        except Exception as e:
            logger.error(f"Failed to retrieve images for user {user_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"이미지 목록 조회 중 오류가 발생했습니다: {str(e)}"
            )


image_service = ImageService()