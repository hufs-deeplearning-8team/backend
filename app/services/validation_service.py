import asyncio
import base64
import logging
import random
import uuid
from typing import List, Dict, Any

from fastapi import HTTPException, status, UploadFile
import sqlalchemy

from app.config import settings
from app.db import database
from app.models import ValidationRecord, Image
from app.schemas import BaseResponse, AIValidationResponse
from app.services.auth_service import auth_service
from app.services.image_service import ImageService
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)


class ValidationService:
    def __init__(self):
        self.auth_service = auth_service
        self.image_service = ImageService()
        self.storage_service = storage_service
    
    async def simulate_ai_validation(self, image_data: bytes, filename: str) -> AIValidationResponse:
        """AI 서버를 시뮬레이션하는 함수 (실제 구현 시 대체될 예정)"""
        await asyncio.sleep(0.5)  # AI 처리 시간 시뮬레이션
        
        # 가짜 데이터 생성
        has_watermark = random.choice([True, False])
        
        # 워터마크가 감지된 경우에만 실제 존재하는 이미지 ID 사용
        detected_id = None
        if has_watermark:
            # 실제 존재하는 이미지 ID 조회
            query = "SELECT id FROM image ORDER BY id ASC LIMIT 1"
            existing_image = await database.fetch_one(query)
            if existing_image:
                detected_id = existing_image["id"]
        
        modification_rate = round(random.uniform(0.0, 0.3), 3) if has_watermark else None
        confidence_score = round(random.uniform(0.7, 0.95), 3)
        
        # 가짜 시각화 이미지 생성 (실제로는 AI 서버에서 변조 부분을 하이라이트한 이미지 반환)
        visualization_image = None
        if has_watermark and modification_rate and modification_rate > 0:
            # 간단한 가짜 시각화 이미지 (실제로는 AI가 생성한 변조 부분 하이라이트 이미지)
            fake_visualization = b"fake_visualization_image_data"
            visualization_image = base64.b64encode(fake_visualization).decode('utf-8')
        
        return AIValidationResponse(
            has_watermark=has_watermark,
            detected_watermark_image_id=detected_id,
            modification_rate=modification_rate,
            confidence_score=confidence_score,
            visualization_image_base64=visualization_image
        )
    
    async def validate_image(self, file: UploadFile, access_token: str) -> BaseResponse:
        """이미지 검증 처리"""
        user_id = self.auth_service.get_user_id_from_token(access_token)
        self.image_service.validate_file(file)
        
        logger.info(f"User {user_id} started validation for file: {file.filename}")
        
        try:
            # 파일 읽기
            contents = await file.read()
            
            # 파일명에서 "protected_" prefix 제거
            original_filename = self.image_service.clean_filename(file.filename)
            
            logger.info(f"Sending image to AI server for validation. Size: {len(contents)} bytes")
            
            # 입력 이미지를 Base64로 인코딩
            input_image_base64 = base64.b64encode(contents).decode('utf-8')
            
            # AI 서버 시뮬레이션 (실제로는 외부 AI 서버에 HTTP 요청)
            ai_response = await self.simulate_ai_validation(contents, original_filename)
            
            
            logger.info(f"AI validation result: watermark={ai_response.has_watermark}, confidence={ai_response.confidence_score}")
            
            # ValidationRecord에 결과 저장
            validation_uuid = str(uuid.uuid4())
            
            query = sqlalchemy.insert(ValidationRecord).values(
                uuid=validation_uuid,
                user_id=int(user_id),
                input_image_filename=original_filename,
                has_watermark=ai_response.has_watermark,
                detected_watermark_image_id=ai_response.detected_watermark_image_id,
                modification_rate=ai_response.modification_rate
            ).returning(ValidationRecord)
            
            validation_record = await database.fetch_one(query)
            
            logger.info(f"Validation record saved with UUID: {validation_uuid}")
            


            # S3에 검증 입력 이미지 저장
            s3_record_path = self.storage_service.get_record_path(validation_uuid, original_filename)
            
            try:
                await self.storage_service.upload_file(contents, s3_record_path)
                logger.info(f"Validation input image saved to S3: {s3_record_path}")
            except Exception as s3_error:
                logger.error(f"Failed to save validation image to S3: {str(s3_error)}")
                # S3 저장 실패해도 검증은 계속 진행
            
            # 응답 데이터 구성
            response_data = {
                "validation_id": validation_uuid,
                "has_watermark": ai_response.has_watermark,
                "detected_watermark_image_id": ai_response.detected_watermark_image_id,
                "modification_rate": ai_response.modification_rate,
                "confidence_score": ai_response.confidence_score,
                "input_filename": original_filename,
                "validation_time": validation_record["time_created"].isoformat() if validation_record else None,
                "input_image_base64": input_image_base64,
                "visualization_image_base64": ai_response.visualization_image_base64
            }
            
            return BaseResponse(
                success=True, 
                description="이미지 검증이 완료되었습니다.", 
                data=[response_data]
            )
            
        except Exception as e:
            logger.error(f"Validation failed for user {user_id}: {str(e)}")
            # 손상된 이미지인지 확인
            if "image" in str(e).lower() or "corrupt" in str(e).lower() or "invalid" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="손상된 이미지 파일입니다"
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"검증 중 오류가 발생했습니다: {str(e)}"
            )
    
    async def get_validation_history(self, access_token: str, limit: int = 10, offset: int = 0) -> BaseResponse:
        """검증 기록 조회"""
        user_id = self.auth_service.get_user_id_from_token(access_token)
        
        logger.info(f"User {user_id} requested validation history (limit={limit}, offset={offset})")
        
        try:
            # 사용자의 검증 기록 조회
            query = (
                ValidationRecord.__table__.select()
                .where(ValidationRecord.user_id == int(user_id))
                .order_by(ValidationRecord.time_created.desc())
                .limit(limit)
                .offset(offset)
            )
            
            records = await database.fetch_all(query)
            
            # 응답 데이터 구성
            history_data = []
            for record in records:
                history_data.append({
                    "validation_id": record["uuid"],
                    "input_filename": record["input_image_filename"],
                    "has_watermark": record["has_watermark"],
                    "detected_watermark_image_id": record["detected_watermark_image_id"],
                    "modification_rate": record["modification_rate"],
                    "validation_time": record["time_created"].isoformat()
                })
            
            logger.info(f"Retrieved {len(history_data)} validation records for user {user_id}")
            
            return BaseResponse(
                success=True,
                description=f"{len(history_data)}개의 검증 기록을 조회했습니다.",
                data=history_data
            )
            
        except Exception as e:
            logger.error(f"Failed to retrieve validation history for user {user_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"검증 기록 조회 중 오류가 발생했습니다: {str(e)}"
            )
    
    async def get_validation_summary(self, access_token: str, limit: int = 10, offset: int = 0) -> BaseResponse:
        """검증 요약 정보 조회"""
        user_id = self.auth_service.get_user_id_from_token(access_token)
        
        logger.info(f"User {user_id} requested validation summary (limit={limit}, offset={offset})")
        
        try:
            # 내가 업로드한 이미지 수 조회
            upload_count_query = (
                sqlalchemy.select(sqlalchemy.func.count(Image.id))
                .where(Image.user_id == int(user_id))
            )
            upload_count_result = await database.fetch_one(upload_count_query)
            total_uploaded_images = upload_count_result[0] if upload_count_result else 0
            
            # 내가 한 검증 횟수 조회
            validation_count_query = (
                sqlalchemy.select(sqlalchemy.func.count(ValidationRecord.id))
                .where(ValidationRecord.user_id == int(user_id))
            )
            validation_count_result = await database.fetch_one(validation_count_query)
            total_validations = validation_count_result[0] if validation_count_result else 0
            
            # 내 검증 내역 조회
            validation_history_query = (
                ValidationRecord.__table__.select()
                .where(ValidationRecord.user_id == int(user_id))
                .order_by(ValidationRecord.time_created.desc())
                .limit(limit)
                .offset(offset)
            )
            
            validation_records = await database.fetch_all(validation_history_query)
            
            # 검증 내역 데이터 구성
            validation_history = []
            for record in validation_records:
                validation_data = {
                    "validation_id": record["uuid"],
                    "record_id": record["id"],
                    "input_filename": record["input_image_filename"],
                    "has_watermark": record["has_watermark"],
                    "detected_watermark_image_id": record["detected_watermark_image_id"],
                    "modification_rate": record["modification_rate"],
                    "validation_time": record["time_created"].isoformat(),
                    "s3_validation_image_url": f"{settings.s3_record_dir}/{record['uuid']}/{record['input_image_filename']}"
                }
                validation_history.append(validation_data)
            
            # 요약 정보 구성
            summary_data = {
                "user_statistics": {
                    "total_uploaded_images": total_uploaded_images,
                    "total_validations": total_validations,
                    "validation_history_count": len(validation_history)
                },
                "validation_history": validation_history
            }
            
            logger.info(f"Retrieved validation summary for user {user_id}: {total_uploaded_images} uploads, {total_validations} validations")
            
            return BaseResponse(
                success=True,
                description="검증 요약 정보를 조회했습니다.",
                data=[summary_data]
            )
            
        except Exception as e:
            logger.error(f"Failed to retrieve validation summary for user {user_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"검증 요약 정보 조회 중 오류가 발생했습니다: {str(e)}"
            )


    async def get_validation_record_by_uuid(self, validation_uuid: str, access_token: str) -> BaseResponse:
        """UUID로 검증 레코드 조회"""
        user_id = self.auth_service.get_user_id_from_token(access_token)
        
        logger.info(f"User {user_id} requested validation record with UUID: {validation_uuid}")
        
        try:
            # UUID로 검증 레코드 조회
            query = (
                ValidationRecord.__table__.select()
                .where(ValidationRecord.uuid.collate('latin1_swedish_ci') == validation_uuid)
            )
            
            record = await database.fetch_one(query)
            
            if not record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="검증 레코드를 찾을 수 없습니다."
                )
            
            # 응답 데이터 구성
            record_data = {
                "validation_id": record["uuid"],
                "record_id": record["id"],
                "user_id": record["user_id"],
                "input_filename": record["input_image_filename"],
                "has_watermark": record["has_watermark"],
                "detected_watermark_image_id": record["detected_watermark_image_id"],
                "modification_rate": record["modification_rate"],
                "validation_time": record["time_created"].isoformat(),
                "s3_path": f"{settings.s3_record_dir}/{record['uuid']}/{record['input_image_filename']}"
            }
            
            logger.info(f"Retrieved validation record: {validation_uuid}")
            
            return BaseResponse(
                success=True,
                description="검증 레코드를 조회했습니다.",
                data=[record_data]
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to retrieve validation record by UUID {validation_uuid}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"검증 레코드 조회 중 오류가 발생했습니다: {str(e)}"
            )
    
    async def get_validation_record_by_id(self, record_id: int, access_token: str) -> BaseResponse:
        """ID로 검증 레코드 조회"""
        user_id = self.auth_service.get_user_id_from_token(access_token)
        
        logger.info(f"User {user_id} requested validation record with ID: {record_id}")
        
        try:
            # ID로 검증 레코드 조회
            query = (
                ValidationRecord.__table__.select()
                .where(ValidationRecord.id == record_id)
            )
            
            record = await database.fetch_one(query)
            
            if not record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="검증 레코드를 찾을 수 없습니다."
                )
            
            # 응답 데이터 구성
            record_data = {
                "validation_id": record["uuid"],
                "record_id": record["id"],
                "user_id": record["user_id"],
                "input_filename": record["input_image_filename"],
                "s3_path": f"{settings.s3_record_dir}/{record['uuid']}/{record['input_image_filename']}",
                "has_watermark": record["has_watermark"],
                "detected_watermark_image_id": record["detected_watermark_image_id"],
                "modification_rate": record["modification_rate"],
                "validation_time": record["time_created"].isoformat(),
            }
            
            logger.info(f"Retrieved validation record ID: {record_id}")
            
            return BaseResponse(
                success=True,
                description="검증 레코드를 조회했습니다.",
                data=[record_data]
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to retrieve validation record by ID {record_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"검증 레코드 조회 중 오류가 발생했습니다: {str(e)}"
            )
    
    async def get_validation_records_by_user_id(self, target_user_id: int, access_token: str, limit: int = 20, offset: int = 0) -> BaseResponse:
        """User ID로 검증 레코드 목록 조회"""
        user_id = self.auth_service.get_user_id_from_token(access_token)
        
        logger.info(f"User {user_id} requested validation records for user {target_user_id} (limit={limit}, offset={offset})")
        
        try:
            # User ID로 검증 레코드 목록 조회
            query = (
                ValidationRecord.__table__.select()
                .where(ValidationRecord.user_id == target_user_id)
                .order_by(ValidationRecord.time_created.desc())
                .limit(limit)
                .offset(offset)
            )
            
            records = await database.fetch_all(query)
            
            # 응답 데이터 구성
            records_data = []
            for record in records:
                record_data = {
                    "validation_id": record["uuid"],
                    "record_id": record["id"],
                    "user_id": record["user_id"],
                    "input_filename": record["input_image_filename"],
                    "has_watermark": record["has_watermark"],
                    "detected_watermark_image_id": record["detected_watermark_image_id"],
                    "modification_rate": record["modification_rate"],
                    "validation_time": record["time_created"].isoformat(),
                    "s3_path": f"{settings.s3_record_dir}/{record['uuid']}/{record['input_image_filename']}"
                }
                records_data.append(record_data)
            
            logger.info(f"Retrieved {len(records_data)} validation records for user {target_user_id}")
            
            return BaseResponse(
                success=True,
                description=f"사용자 {target_user_id}의 {len(records_data)}개 검증 레코드를 조회했습니다.",
                data=records_data
            )
            
        except Exception as e:
            logger.error(f"Failed to retrieve validation records for user {target_user_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"검증 레코드 조회 중 오류가 발생했습니다: {str(e)}"
            )


validation_service = ValidationService()