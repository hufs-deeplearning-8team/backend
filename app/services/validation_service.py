import asyncio
import base64
import logging
import random
import uuid
from typing import List, Dict, Any
import numpy as np
from PIL import Image as PILImage
import io

from fastapi import HTTPException, status, UploadFile
import sqlalchemy

from app.config import settings
from app.db import database
from app.models import ValidationRecord, Image, ProtectionAlgorithm
from app.schemas import BaseResponse, AIValidationResponse, UserReportRequest, UserReportResponse
from app.services.auth_service import auth_service
from app.services.image_service import ImageService
from app.services.storage_service import storage_service
from app.services.email_service import email_service

logger = logging.getLogger(__name__)


class ValidationService:
    def __init__(self):
        self.auth_service = auth_service
        self.image_service = ImageService()
        self.storage_service = storage_service
    
    async def simulate_ai_validation(self, image_data: bytes, filename: str, algorithm: str) -> AIValidationResponse:
        """AI 서버를 시뮬레이션하는 함수 (실제 구현 시 대체될 예정)"""
        logger.info(f"Simulating AI validation with algorithm: {algorithm}")
        
        # TODO: 실제 AI 서버 요청 구현
        # 실제 구현 시 다음과 같은 형태로 AI 서버에 요청
        """
        ai_request_payload = {
            "image_base64": base64.b64encode(image_data).decode('utf-8'),
            "filename": filename,
            "validation_algorithm": algorithm,
            "detection_mode": "watermark_detection",
            "return_visualization": True
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AI_SERVER_URL}/validate", 
                json=ai_request_payload,
                timeout=30.0
            )
            ai_result = response.json()
        """
        
        await asyncio.sleep(0.5)  # AI 처리 시간 시뮬레이션
        
        # 단일 알고리즘(EditGuard) 결과 시뮬레이션
        has_watermark = random.choice([True, True, False])
        
        # 워터마크가 감지된 경우에만 실제 존재하는 이미지 ID 사용
        detected_id = None
        if has_watermark:
            # 실제 존재하는 이미지 ID 조회
            query = "SELECT id FROM image ORDER BY id ASC LIMIT 1"
            existing_image = await database.fetch_one(query)
            if existing_image:
                detected_id = existing_image["id"]
        
        modification_rate = round(random.uniform(0.0, 0.3), 3) if has_watermark else None
        # confidence_score = round(random.uniform(0.7, 0.95), 3)
        
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
            # confidence_score=confidence_score,
            visualization_image_base64=visualization_image
        )
    
    async def validate_image(self, file: UploadFile, validation_algorithm: str, access_token: str) -> BaseResponse:
        """이미지 검증 처리"""
        user_id = self.auth_service.get_user_id_from_token(access_token)
        self.image_service.validate_file(file)
        
        # validation_algorithm 검증
        try:
            validation_enum = ProtectionAlgorithm(validation_algorithm)
        except ValueError:
            valid_algorithms = [alg.value for alg in ProtectionAlgorithm]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"유효하지 않은 검증 알고리즘입니다. 사용 가능한 값: {valid_algorithms}"
            )
        
        logger.info(f"User {user_id} started validation for file: {file.filename} with algorithm: {validation_algorithm}")
        
        try:
            # 파일 읽기
            contents = await file.read()
            
            # 파일명에서 "protected_" prefix 제거
            original_filename = self.image_service.clean_filename(file.filename)
            
            logger.info(f"Sending image to AI server for validation. Size: {len(contents)} bytes")
            
            # 입력 이미지를 Base64로 인코딩
            input_image_base64 = base64.b64encode(contents).decode('utf-8')
            

            # 실제 AI 서버를 통한 이미지 검증
            verification_result = await self.image_service._send_to_ai_server_for_verification(contents, validation_enum)
            logger.info(f"AI 서버 검증 응답: {verification_result}")
            
            # recovered_bit에서 복구된 image ID 검증
            original_image_id = verification_result.get("original_image_id", None)
            logger.info(f"검증 알고리즘: {validation_enum}, 복구된 이미지 ID: {original_image_id}")
            
            if original_image_id and original_image_id > 0:
                # DB에서 해당 image ID가 존재하는지 확인
                image_check_query = sqlalchemy.select(Image.id).where(Image.id == original_image_id)
                existing_image = await database.fetch_one(image_check_query)
                
                if not existing_image:
                    logger.error(f"복구된 image ID {original_image_id}가 DB에 존재하지 않습니다.")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"검증 실패: 복구된 원본 이미지 ID({original_image_id})가 시스템에 존재하지 않습니다."
                    )
                logger.info(f"복구된 image ID {original_image_id} 존재 확인 완료")
                
                # EditGuard 모델 특별 처리: 픽셀 비교 기반 마스크 생성
                if validation_enum == ProtectionAlgorithm.EditGuard:
                    await self._process_pixel_comparison_validation(
                        contents, original_image_id, verification_result, validation_enum
                    )
            else:
                # original_image_id가 없는 경우 처리
                logger.info(f"original_image_id가 없습니다: {original_image_id}")
                
                if validation_enum == ProtectionAlgorithm.EditGuard:
                    logger.info(f"{validation_enum.value}: original_image_id 없음. AI 서버 응답 기반으로 처리합니다.")
                    # AI 서버에서 받은 기본 변조률과 mask 사용
                    # (실제 프로덕션에서는 다른 로직 구현 가능)

            # AI 응답을 AIValidationResponse 형식으로 변환
            calculated_rate = verification_result.get("tampering_rate", 0)
            mask_data = verification_result.get("tampered_regions_mask", "")
            
            ai_response = AIValidationResponse(
                has_watermark=original_image_id is not None and original_image_id > 0,
                detected_watermark_image_id=original_image_id,
                modification_rate=calculated_rate,
                visualization_image_base64=mask_data
            )
            
            
            logger.info(f"AI validation result: watermark={ai_response.has_watermark}, modification_rate={ai_response.modification_rate}, detected_id={ai_response.detected_watermark_image_id}")
            
            # ValidationRecord에 결과 저장
            validation_uuid = str(uuid.uuid4())
            
            from app.models import kst_now
            
            query = sqlalchemy.insert(ValidationRecord).values(
                uuid=validation_uuid,
                user_id=int(user_id),
                input_image_filename=original_filename,
                has_watermark=ai_response.has_watermark,
                detected_watermark_image_id=ai_response.detected_watermark_image_id,
                modification_rate=ai_response.modification_rate,
                validation_algorithm=validation_enum,
                time_created=kst_now()
            ).returning(ValidationRecord)


            validation_record = await database.fetch_one(query)
            
            logger.info(f"Validation record saved with UUID: {validation_uuid}")
            
            # S3에 검증 입력 이미지 저장
            s3_record_path = self.storage_service.get_record_path(validation_uuid, original_filename)
            
            try:
                await self.storage_service.upload_file(contents, s3_record_path)
                logger.info(f"Validation input image saved to S3: {s3_record_path}")
                
                # mask 이미지 S3에 저장
                if ai_response.visualization_image_base64:
                    mask_bytes = base64.b64decode(ai_response.visualization_image_base64)
                    mask_s3_path = f"record/{validation_uuid}/mask.png"
                    await self.storage_service.upload_file(mask_bytes, mask_s3_path)
                    
                    logger.info(f"{validation_enum.value} generated mask image saved to S3: {mask_s3_path}")
                    
                    # 원본 이미지와 mask를 합성한 이미지 생성
                    try:
                        combined_bytes = self._create_combined_image(contents, mask_bytes)
                        combined_s3_path = f"record/{validation_uuid}/combined.png"
                        await self.storage_service.upload_file(combined_bytes, combined_s3_path)
                        logger.info(f"Combined image saved to S3: {combined_s3_path}")
                    except Exception as combine_error:
                        logger.error(f"Failed to create combined image: {str(combine_error)}")
                else:
                    logger.info(f"{validation_enum.value}: No tampering detected, empty mask generated")
                    
            except Exception as s3_error:
                logger.error(f"Failed to save validation images to S3: {str(s3_error)}")
                # S3 저장 실패해도 검증은 계속 진행
            
            # 이메일 발송을 위해 원본 이미지 소유자 확인
            original_image_owner_id = None
            if ai_response.has_watermark and ai_response.detected_watermark_image_id:
                image_owner_query = sqlalchemy.select(Image.user_id).where(Image.id == ai_response.detected_watermark_image_id)
                image_owner_record = await database.fetch_one(image_owner_query)
                if image_owner_record:
                    original_image_owner_id = image_owner_record["user_id"]
            
            # 본인이 본인 이미지를 검증하는 경우가 아닐 때만 이메일 발송
            if ai_response.has_watermark and ai_response.detected_watermark_image_id and original_image_owner_id and original_image_owner_id != int(user_id):
                # 위변조 검출 시 원저작자에게 이메일 발송
                if ai_response.modification_rate and ai_response.modification_rate > 0.05:
                    await self._send_forgery_detection_email(
                        validation_uuid=validation_uuid,
                        detected_image_id=ai_response.detected_watermark_image_id,
                        detection_info={
                            "detection_time": validation_record["time_created"].strftime("%Y-%m-%d %H:%M:%S") if validation_record else None,
                            "image_name": original_filename,
                            "confidence_score": round(ai_response.modification_rate, 2),
                            "detection_method": validation_enum.value
                        },
                        tampered_image_url=f"https://{settings.S3_DEPLOYMENT_BUCKET}.s3.{settings.AWS_REGION_NAME}.amazonaws.com/record/{validation_uuid}/{original_filename}"
                    )
                # 원본 확인 시 원저작자에게 알림 이메일 발송 (워터마크 감지되었지만 변조율이 매우 낮은 경우)
                else:
                    await self._send_original_confirmation_email(
                        validation_uuid=validation_uuid,
                        detected_image_id=ai_response.detected_watermark_image_id,
                        confirmation_info={
                            "confirmation_time": validation_record["time_created"].strftime("%Y-%m-%d %H:%M:%S") if validation_record else None,
                            "image_name": original_filename,
                            "image_number": ai_response.detected_watermark_image_id,
                            "verification_method": validation_enum.value
                        },
                        validated_image_url=f"https://{settings.S3_DEPLOYMENT_BUCKET}.s3.{settings.AWS_REGION_NAME}.amazonaws.com/record/{validation_uuid}/{original_filename}"
                    )
            
            # 응답 데이터 구성
            response_data = {
                "validation_id": validation_uuid,
                "has_watermark": ai_response.has_watermark,
                "detected_watermark_image_id": ai_response.detected_watermark_image_id,
                "modification_rate": ai_response.modification_rate,
                "validation_algorithm": validation_enum.value,  # 사용된 검증 알고리즘
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
                    "validation_algorithm": record["validation_algorithm"],
                    "validation_time": record["time_created"].isoformat(),
                    "s3_validation_image_url": f"{settings.s3_record_dir}/{record['uuid']}/{record['input_image_filename']}",
                    "s3_mask_url": f"{settings.s3_record_dir}/{record['uuid']}/mask.png"
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
                    "validation_algorithm": record["validation_algorithm"],
                    "validation_time": record["time_created"].isoformat(),
                    "s3_validation_image_url": f"{settings.s3_record_dir}/{record['uuid']}/{record['input_image_filename']}",
                    "s3_mask_url": f"{settings.s3_record_dir}/{record['uuid']}/mask.png"
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
                .where(ValidationRecord.uuid.collate('utf8mb4_general_ci') == validation_uuid)
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
                "validation_algorithm": record["validation_algorithm"],
                "validation_time": record["time_created"].isoformat(),
                "s3_path": f"{settings.s3_record_dir}/{record['uuid']}/{record['input_image_filename']}",
                "s3_mask_url": f"{settings.s3_record_dir}/{record['uuid']}/mask.png"
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
                "s3_mask_url": f"{settings.s3_record_dir}/{record['uuid']}/mask.png"
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
                    "validation_algorithm": record["validation_algorithm"],
                    "validation_time": record["time_created"].isoformat(),
                    "s3_path": f"{settings.s3_record_dir}/{record['uuid']}/{record['input_image_filename']}",
                    "s3_mask_url": f"{settings.s3_record_dir}/{record['uuid']}/mask.png"
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
    
    # 픽셀 비교 기반 마스크 생성 관련 상수
    PIXEL_DIFF_THRESHOLD = 10  # RGB 값 차이 임계값
    TAMPERED_COLOR = [255, 255, 255, 255]  # 하얀색, 불투명
    NORMAL_COLOR = [0, 0, 0, 0]  # 투명

    async def _create_difference_mask(self, input_image_bytes: bytes, original_sr_h_bytes: bytes) -> tuple[str, float]:
        """EditGuard용 픽셀 차이 기반 마스크 생성"""
        try:
            # 이미지 로드 및 전처리
            input_image, original_image = self._load_and_preprocess_images(
                input_image_bytes, original_sr_h_bytes
            )
            
            # 픽셀 차이 계산 및 변조 마스크 생성
            tampered_mask = self._calculate_pixel_differences(input_image, original_image)
            
            # 변조률 계산
            tampering_rate = self._calculate_tampering_rate(tampered_mask)
            
            # 마스크 이미지 생성 및 인코딩
            mask_base64 = self._create_mask_image(tampered_mask)
            
            logger.info(
                f"픽셀 비교 마스크 생성 완료: 변조률 {tampering_rate:.2f}% "
                f"({np.sum(tampered_mask)}/{tampered_mask.size} 픽셀)"
            )
            
            return mask_base64, tampering_rate
            
        except Exception as e:
            logger.error(f"픽셀 비교 마스크 생성 중 오류: {str(e)}")
            return "", 0.0
    
    def _load_and_preprocess_images(self, input_bytes: bytes, original_bytes: bytes) -> tuple:
        """이미지 로드 및 전처리"""
        import io
        from PIL import Image as PILImage
        
        # 이미지 로드
        input_image = PILImage.open(io.BytesIO(input_bytes))
        original_image = PILImage.open(io.BytesIO(original_bytes))
        
        # 크기 맞춤
        if input_image.size != original_image.size:
            input_image = input_image.resize(original_image.size)
        
        # RGB 모드로 통일
        input_image = input_image.convert('RGB')
        original_image = original_image.convert('RGB')
        
        return input_image, original_image
    
    def _calculate_pixel_differences(self, input_image, original_image) -> np.ndarray:
        """픽셀 차이 계산 및 변조 마스크 생성"""
        import numpy as np
        
        # numpy 배열로 변환
        input_array = np.array(input_image, dtype=np.float32)
        original_array = np.array(original_image, dtype=np.float32)
        
        # RGB 차이의 유클리드 거리 계산
        diff = input_array - original_array
        diff_magnitude = np.sqrt(np.sum(diff ** 2, axis=2))
        
        # 임계값을 넘는 픽셀을 변조된 것으로 판단
        return diff_magnitude > self.PIXEL_DIFF_THRESHOLD
    
    def _calculate_tampering_rate(self, tampered_mask: np.ndarray) -> float:
        """변조률 계산"""
        total_pixels = tampered_mask.size
        tampered_pixels = np.sum(tampered_mask)
        return (tampered_pixels / total_pixels * 100) if total_pixels > 0 else 0.0
    
    def _create_mask_image(self, tampered_mask: np.ndarray) -> str:
        """마스크 이미지 생성 및 base64 인코딩"""
        import numpy as np
        import base64
        import io
        from PIL import Image as PILImage
        
        # RGBA 마스크 이미지 생성
        mask_image = np.zeros((*tampered_mask.shape, 4), dtype=np.uint8)
        mask_image[tampered_mask] = self.TAMPERED_COLOR  # 변조된 부분: 하얀색
        mask_image[~tampered_mask] = self.NORMAL_COLOR   # 정상 부분: 투명
        
        # PIL 이미지로 변환 후 base64 인코딩
        mask_pil = PILImage.fromarray(mask_image, mode='RGBA')
        mask_buffer = io.BytesIO()
        mask_pil.save(mask_buffer, format='PNG')
        
        return base64.b64encode(mask_buffer.getvalue()).decode('utf-8')
    
    def _create_empty_mask(self) -> str:
        """빈 마스크 이미지 생성 (변조가 없는 경우)"""
        import numpy as np
        import base64
        import io
        from PIL import Image as PILImage
        
        # 기본 크기의 빈 마스크 생성 (512x512)
        default_size = (512, 512)
        mask_image = np.zeros((*default_size, 4), dtype=np.uint8)
        mask_image[:, :] = self.NORMAL_COLOR  # 모든 픽셀을 투명으로 설정
        
        # PIL 이미지로 변환 후 base64 인코딩
        mask_pil = PILImage.fromarray(mask_image, mode='RGBA')
        mask_buffer = io.BytesIO()
        mask_pil.save(mask_buffer, format='PNG')
        
        return base64.b64encode(mask_buffer.getvalue()).decode('utf-8')
    
    async def _process_pixel_comparison_validation(self, input_image_bytes: bytes, original_image_id: int, verification_result: dict, validation_enum: ProtectionAlgorithm) -> None:
        """픽셀 비교 기반 검증 처리"""
        try:
            # 원본 이미지 정보를 DB에서 조회하여 파일명 가져오기
            image_query = sqlalchemy.select(Image.filename).where(Image.id == original_image_id)
            image_record = await database.fetch_one(image_query)
            
            if not image_record:
                logger.error(f"원본 이미지 ID {original_image_id}를 DB에서 찾을 수 없습니다.")
                return
            
            # 새로운 파일명 형식으로 sr_h 경로 생성
            original_filename = image_record["filename"]
            filename_without_ext = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
            original_sr_h_path = f"image/{original_image_id}/{filename_without_ext}_wm.png"
            
            # 원본 워터마크 이미지 다운로드
            original_sr_h_bytes = await self.storage_service.download_file(original_sr_h_path)
            
            # 픽셀 비교 기반 마스크 및 변조률 생성
            mask_data, tampering_rate = await self._create_difference_mask(
                input_image_bytes, original_sr_h_bytes
            )
            
            # 결과 업데이트
            self._update_verification_result(verification_result, mask_data, tampering_rate, original_image_id, validation_enum)
            
        except Exception as error:
            logger.warning(f"{validation_enum.value} 검증 처리 중 오류: {str(error)}. 기존 AI 서버 결과 유지")
            # 오류 발생 시 기존 AI 서버 결과 그대로 사용
    
    def _update_verification_result(self, verification_result: dict, mask_data: str, tampering_rate: float, original_image_id: int, validation_enum: ProtectionAlgorithm) -> None:
        """검증 결과 업데이트"""
        if tampering_rate == 0.0:
            logger.info(f"{validation_enum.value}: 입력 이미지와 원본 이미지(ID: {original_image_id}) 일치 - 변조 없음")
            # 변조가 없는 경우에도 빈 마스크 이미지 생성
            empty_mask_data = self._create_empty_mask()
            verification_result.update({
                "tampering_rate": 0.0,
                "tampered_regions_mask": empty_mask_data
            })
        else:
            logger.info(f"{validation_enum.value}: 변조 감지 - 변조률: {tampering_rate:.2f}% (원본 ID: {original_image_id})")
            verification_result.update({
                "tampering_rate": tampering_rate,
                "tampered_regions_mask": mask_data
            })
    
    async def _compare_images(self, image1_bytes: bytes, image2_bytes: bytes) -> bool:
        """두 이미지가 동일한지 비교"""
        try:
            from PIL import Image as PILImage
            import io
            
            # 첫 번째 이미지 로드
            image1 = PILImage.open(io.BytesIO(image1_bytes))
            # 두 번째 이미지 로드
            image2 = PILImage.open(io.BytesIO(image2_bytes))
            
            # 이미지 크기가 다르면 다른 이미지
            if image1.size != image2.size:
                return False
            
            # 이미지 모드가 다르면 RGB로 통일
            if image1.mode != image2.mode:
                image1 = image1.convert('RGB')
                image2 = image2.convert('RGB')
            
            # numpy 배열로 변환하여 픽셀 단위 비교
            import numpy as np
            array1 = np.array(image1)
            array2 = np.array(image2)
            
            # 모든 픽셀이 동일한지 확인
            return np.array_equal(array1, array2)
            
        except Exception as e:
            logger.error(f"이미지 비교 중 오류: {str(e)}")
            return False
    
    def _create_combined_image(self, original_bytes: bytes, mask_bytes: bytes) -> bytes:
        """원본 이미지와 mask를 합성한 이미지 생성"""
        try:
            from PIL import Image as PILImage
            import io
            
            # 원본 이미지 로드
            original_image = PILImage.open(io.BytesIO(original_bytes))
            # mask 이미지 로드
            mask_image = PILImage.open(io.BytesIO(mask_bytes))
            
            # 이미지 크기를 원본에 맞춤
            if mask_image.size != original_image.size:
                mask_image = mask_image.resize(original_image.size)
            
            # RGB 모드로 통일
            if original_image.mode != 'RGB':
                original_image = original_image.convert('RGB')
            if mask_image.mode != 'RGB':
                mask_image = mask_image.convert('RGB')
            
            # mask를 반투명하게 겹침
            combined = PILImage.blend(original_image, mask_image, alpha=0.3)
            
            # bytes로 변환
            output = io.BytesIO()
            combined.save(output, format='PNG')
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"이미지 합성 중 오류: {str(e)}")
            # 실패 시 원본 이미지 반환
            return original_bytes

    async def _send_forgery_detection_email(
        self,
        validation_uuid: str,
        detected_image_id: int,
        detection_info: dict,
        tampered_image_url: str
    ) -> None:
        """위변조 검출 시 원저작자에게 이메일 발송"""
        try:
            # 원본 이미지 정보 조회
            image_query = sqlalchemy.select(Image).where(Image.id == detected_image_id)
            image_record = await database.fetch_one(image_query)
            
            if not image_record:
                logger.error(f"원본 이미지 ID {detected_image_id}를 찾을 수 없습니다.")
                return
            
            # 원저작자 정보 조회
            from app.models import User
            user_id_val = image_record.user_id if hasattr(image_record, 'user_id') else image_record["user_id"]
            user_query = sqlalchemy.select(User).where(User.id == user_id_val)
            user_record = await database.fetch_one(user_query)
            
            if not user_record:
                user_id_val = image_record.user_id if hasattr(image_record, 'user_id') else image_record["user_id"]
                logger.error(f"사용자 ID {user_id_val}를 찾을 수 없습니다.")
                return
            
            # 원본 이미지 URL들 생성
            filename = image_record.filename if hasattr(image_record, 'filename') else image_record["filename"]
            filename_without_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
            original_image_url = f"https://{settings.S3_DEPLOYMENT_BUCKET}.s3.{settings.AWS_REGION_NAME}.amazonaws.com/image/{detected_image_id}/{filename_without_ext}_origi.png"
            watermark_image_url = f"https://{settings.S3_DEPLOYMENT_BUCKET}.s3.{settings.AWS_REGION_NAME}.amazonaws.com/image/{detected_image_id}/{filename_without_ext}_wm.png"
            
            # 원본 이미지 정보 추가
            upload_time = image_record.time_created if hasattr(image_record, 'time_created') else image_record["time_created"]
            copyright_info = getattr(image_record, 'copyright', None) if hasattr(image_record, 'copyright') else image_record.get("copyright", "저작권자 정보 없음")
            
            original_image_info = {
                "image_id": detected_image_id,
                "filename": filename,
                "upload_time": upload_time.strftime("%Y-%m-%d %H:%M:%S") if upload_time else "N/A",
                "copyright_info": copyright_info or "저작권자 정보 없음",
                "original_image_url": original_image_url,
                "watermark_image_url": watermark_image_url
            }
            
            # 보고서 URL 생성
            report_url = f"https://aegis.gdgoc.com/result/{validation_uuid}"
            
            # 이메일 발송
            user_email = user_record.email if hasattr(user_record, 'email') else user_record["email"]
            username = user_record.name if hasattr(user_record, 'name') else user_record["name"]
            
            success = await email_service.send_forgery_detection_email(
                user_email=user_email,
                username=username,
                detection_info=detection_info,
                report_url=report_url,
                image_url=tampered_image_url,
                original_image_info=original_image_info
            )
            
            if success:
                logger.info(f"위변조 검출 이메일 발송 성공: {user_email} (이미지 ID: {detected_image_id})")
            else:
                logger.error(f"위변조 검출 이메일 발송 실패: {user_email} (이미지 ID: {detected_image_id})")
                
        except Exception as e:
            import traceback
            logger.error(f"위변조 검출 이메일 발송 중 오류: {str(e)}")
            logger.error(f"상세 오류: {traceback.format_exc()}")

    async def _send_original_confirmation_email(
        self,
        validation_uuid: str,
        detected_image_id: int,
        confirmation_info: dict,
        validated_image_url: str
    ) -> None:
        """원본 확인 시 원저작자에게 알림 이메일 발송"""
        try:
            # 원본 이미지 정보 조회
            image_query = sqlalchemy.select(Image).where(Image.id == detected_image_id)
            image_record = await database.fetch_one(image_query)
            
            if not image_record:
                logger.error(f"원본 이미지 ID {detected_image_id}를 찾을 수 없습니다.")
                return
            
            # 원저작자 정보 조회
            from app.models import User
            user_id_val = image_record.user_id if hasattr(image_record, 'user_id') else image_record["user_id"]
            user_query = sqlalchemy.select(User).where(User.id == user_id_val)
            user_record = await database.fetch_one(user_query)
            
            if not user_record:
                logger.error(f"사용자 ID {user_id_val}를 찾을 수 없습니다.")
                return
            
            # 원본 이미지 URL들 생성
            filename = image_record.filename if hasattr(image_record, 'filename') else image_record["filename"]
            filename_without_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
            original_image_url = f"https://{settings.S3_DEPLOYMENT_BUCKET}.s3.{settings.AWS_REGION_NAME}.amazonaws.com/image/{detected_image_id}/{filename_without_ext}_origi.png"
            watermark_image_url = f"https://{settings.S3_DEPLOYMENT_BUCKET}.s3.{settings.AWS_REGION_NAME}.amazonaws.com/image/{detected_image_id}/{filename_without_ext}_wm.png"
            
            # 원본 이미지 정보 추가
            upload_time = image_record.time_created if hasattr(image_record, 'time_created') else image_record["time_created"]
            copyright_info = getattr(image_record, 'copyright', None) if hasattr(image_record, 'copyright') else image_record.get("copyright", "저작권자 정보 없음")
            
            original_image_info = {
                "image_id": detected_image_id,
                "filename": filename,
                "upload_time": upload_time.strftime("%Y-%m-%d %H:%M:%S") if upload_time else "N/A",
                "copyright_info": copyright_info or "저작권자 정보 없음",
                "original_image_url": original_image_url,
                "watermark_image_url": watermark_image_url
            }
            
            # 보고서 URL 생성
            report_url = f"https://aegis.gdgoc.com/result/{validation_uuid}"
            
            # 이메일 발송
            user_email = user_record.email if hasattr(user_record, 'email') else user_record["email"]
            username = user_record.name if hasattr(user_record, 'name') else user_record["name"]
            
            success = await email_service.send_original_confirmation_email(
                user_email=user_email,
                username=username,
                confirmation_info=confirmation_info,
                report_url=report_url,
                image_url=validated_image_url,
                original_image_info=original_image_info
            )
            
            if success:
                logger.info(f"원본 확인 알림 이메일 발송 성공: {user_email} (이미지 ID: {detected_image_id})")
            else:
                logger.error(f"원본 확인 알림 이메일 발송 실패: {user_email} (이미지 ID: {detected_image_id})")
                
        except Exception as e:
            import traceback
            logger.error(f"원본 확인 알림 이메일 발송 중 오류: {str(e)}")
            logger.error(f"상세 오류: {traceback.format_exc()}")

    async def get_validation_record_by_uuid_public(self, validation_uuid: str) -> BaseResponse:
        """UUID로 검증 레코드 조회 (인증 불필요)"""
        logger.info(f"Public request for validation record with UUID: {validation_uuid}")
        
        try:
            # UUID로 검증 레코드 조회
            query = (
                ValidationRecord.__table__.select()
                .where(ValidationRecord.uuid.collate('utf8mb4_general_ci') == validation_uuid)
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
                "validation_algorithm": record["validation_algorithm"],
                "validation_time": record["time_created"].isoformat(),
                "s3_path": f"{settings.s3_record_dir}/{record['uuid']}/{record['input_image_filename']}",
                "s3_mask_url": f"{settings.s3_record_dir}/{record['uuid']}/mask.png",
                "user_report_link": record["user_report_link"],
                "user_report_text": record["user_report_text"]
            }
            
            logger.info(f"Public retrieved validation record: {validation_uuid}")
            
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
    
    async def get_validation_record_by_id_public(self, record_id: int) -> BaseResponse:
        """ID로 검증 레코드 조회 (인증 불필요)"""
        logger.info(f"Public request for validation record with ID: {record_id}")
        
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
                "validation_algorithm": record["validation_algorithm"],
                "validation_time": record["time_created"].isoformat(),
                "s3_mask_url": f"{settings.s3_record_dir}/{record['uuid']}/mask.png"
            }
            
            logger.info(f"Public retrieved validation record ID: {record_id}")
            
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
    
    async def get_validation_records_by_user_id_public(self, target_user_id: int, limit: int = 20, offset: int = 0) -> BaseResponse:
        """User ID로 검증 레코드 목록 조회 (인증 불필요)"""
        logger.info(f"Public request for validation records for user {target_user_id} (limit={limit}, offset={offset})")
        
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
                    "validation_algorithm": record["validation_algorithm"],
                    "validation_time": record["time_created"].isoformat(),
                    "s3_path": f"{settings.s3_record_dir}/{record['uuid']}/{record['input_image_filename']}",
                    "s3_mask_url": f"{settings.s3_record_dir}/{record['uuid']}/mask.png"
                }
                records_data.append(record_data)
            
            logger.info(f"Public retrieved {len(records_data)} validation records for user {target_user_id}")
            
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

    async def update_user_report(self, report_data: UserReportRequest, access_token: str) -> BaseResponse:
        """사용자 제보 정보 업데이트"""
        user_id = self.auth_service.get_user_id_from_token(access_token)
        
        logger.info(f"User {user_id} updating report for validation UUID: {report_data.validation_uuid}")
        
        try:
            # 검증 레코드 조회 및 권한 확인
            query = (
                ValidationRecord.__table__.select()
                .where(ValidationRecord.uuid.collate('utf8mb4_general_ci') == report_data.validation_uuid)
            )
            
            record = await database.fetch_one(query)
            
            if not record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="검증 레코드를 찾을 수 없습니다."
                )
            
            # 해당 검증을 수행한 사용자인지 확인
            if record["user_id"] != int(user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="본인이 수행한 검증에 대해서만 제보할 수 있습니다."
                )
            
            # 위변조가 검출된 검증인지 확인
            if not record["has_watermark"] or not record["modification_rate"] or record["modification_rate"] <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="위변조가 검출되지 않은 검증에는 제보할 수 없습니다."
                )
            
            # 사용자 제보 정보 업데이트
            update_query = (
                sqlalchemy.update(ValidationRecord)
                .where(ValidationRecord.uuid.collate('utf8mb4_general_ci') == report_data.validation_uuid)
                .values(
                    user_report_link=report_data.report_link,
                    user_report_text=report_data.report_text
                )
            )
            
            # MariaDB는 RETURNING을 지원하지 않으므로 별도로 UPDATE 후 SELECT
            await database.execute(update_query)
            
            # 업데이트된 레코드 조회
            select_query = (
                ValidationRecord.__table__.select()
                .where(ValidationRecord.uuid.collate('utf8mb4_general_ci') == report_data.validation_uuid)
            )
            updated_record = await database.fetch_one(select_query)
            
            if not updated_record:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="제보 정보 업데이트에 실패했습니다."
                )
            
            logger.info(f"User report updated successfully for validation UUID: {report_data.validation_uuid}")
            
            # 응답 데이터 구성
            response_data = UserReportResponse(
                validation_uuid=report_data.validation_uuid,
                report_link=report_data.report_link,
                report_text=report_data.report_text,
                updated_time=updated_record["time_created"].isoformat()
            )
            
            return BaseResponse(
                success=True,
                description="사용자 제보 정보가 성공적으로 업데이트되었습니다.",
                data=[response_data.model_dump()]
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update user report for validation {report_data.validation_uuid}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"제보 정보 업데이트 중 오류가 발생했습니다: {str(e)}"
            )

    async def get_validation_summary2(self, access_token: str, limit: int = 20, offset: int = 0) -> BaseResponse:
        """통합 검증 요약 정보 조회 - 내가 검증한 것과 내 이미지가 검증된 것 모두 포함"""
        user_id = self.auth_service.get_user_id_from_token(access_token)
        
        logger.info(f"User {user_id} requesting integrated validation summary with limit {limit}, offset {offset}")
        
        try:
            from app.models import Image
            
            # 모든 레코드를 하나의 리스트로 수집
            all_records = []
            
            # 1. 내가 검증한 레코드들 조회
            my_validation_query = (
                ValidationRecord.__table__.select()
                .where(ValidationRecord.user_id == int(user_id))
                .order_by(ValidationRecord.time_created.desc())
            )
            my_validation_records = await database.fetch_all(my_validation_query)
            
            # 2. 내 이미지가 검증된 레코드들 조회 (내가 검증한 것 제외)
            my_image_validation_query = (
                ValidationRecord.__table__.select()
                .select_from(
                    ValidationRecord.__table__.join(
                        Image.__table__, 
                        ValidationRecord.detected_watermark_image_id == Image.id
                    )
                )
                .where(
                    sqlalchemy.and_(
                        Image.user_id == int(user_id),
                        ValidationRecord.user_id != int(user_id)
                    )
                )
                .order_by(ValidationRecord.time_created.desc())
            )
            my_image_validation_records = await database.fetch_all(my_image_validation_query)
            
            # 각 레코드에 relation_type과 원본 이미지 정보 추가
            for record in my_validation_records:
                record_dict = dict(record)
                
                # 원본 이미지 정보 조회
                if record_dict["detected_watermark_image_id"]:
                    image_query = (
                        Image.__table__.select()
                        .where(Image.id == record_dict["detected_watermark_image_id"])
                    )
                    image_record = await database.fetch_one(image_query)
                    
                    if image_record:
                        # 내가 검증했고 대상도 내 이미지인 경우 (relation_type = 3)
                        if image_record["user_id"] == int(user_id):
                            record_dict["relation_type"] = 3
                        else:
                            record_dict["relation_type"] = 1
                        
                        record_dict["original_image_owner_id"] = image_record["user_id"]
                        record_dict["original_image_filename"] = image_record["filename"]
                        record_dict["original_image_copyright"] = image_record["copyright"]
                    else:
                        record_dict["relation_type"] = 1
                        record_dict["original_image_owner_id"] = None
                        record_dict["original_image_filename"] = None
                        record_dict["original_image_copyright"] = None
                else:
                    record_dict["relation_type"] = 1
                    record_dict["original_image_owner_id"] = None
                    record_dict["original_image_filename"] = None
                    record_dict["original_image_copyright"] = None
                
                all_records.append(record_dict)
            
            # 내 이미지가 검증된 레코드들 처리 (relation_type = 2)
            for record in my_image_validation_records:
                record_dict = dict(record)
                record_dict["relation_type"] = 2
                
                # 원본 이미지 정보 조회
                if record_dict["detected_watermark_image_id"]:
                    image_query = (
                        Image.__table__.select()
                        .where(Image.id == record_dict["detected_watermark_image_id"])
                    )
                    image_record = await database.fetch_one(image_query)
                    
                    if image_record:
                        record_dict["original_image_owner_id"] = image_record["user_id"]
                        record_dict["original_image_filename"] = image_record["filename"]
                        record_dict["original_image_copyright"] = image_record["copyright"]
                    else:
                        record_dict["original_image_owner_id"] = None
                        record_dict["original_image_filename"] = None
                        record_dict["original_image_copyright"] = None
                else:
                    record_dict["original_image_owner_id"] = None
                    record_dict["original_image_filename"] = None
                    record_dict["original_image_copyright"] = None
                
                all_records.append(record_dict)
            
            # 시간순 정렬
            all_records.sort(key=lambda x: x["time_created"], reverse=True)
            
            # 페이지네이션 적용
            records = all_records[offset:offset + limit]
            
            # 통계 계산
            my_validations_count = len([r for r in all_records if r["relation_type"] == 1])
            my_image_validations_count = len([r for r in all_records if r["relation_type"] == 2])
            self_validations_count = len([r for r in all_records if r["relation_type"] == 3])
            total_records_count = len(all_records)
            
            # 응답 데이터 구성
            validation_records = []
            for record in records:
                record_data = {
                    "validation_id": record["uuid"],
                    "record_id": record["id"],
                    "user_id": record["user_id"],
                    "input_filename": record["input_image_filename"],
                    "has_watermark": record["has_watermark"],
                    "detected_watermark_image_id": record["detected_watermark_image_id"],
                    "modification_rate": record["modification_rate"],
                    "validation_algorithm": record["validation_algorithm"],
                    "validation_time": record["time_created"].isoformat(),
                    "s3_validation_image_url": f"{settings.s3_record_dir}/{record['uuid']}/{record['input_image_filename']}",
                    "s3_mask_url": f"{settings.s3_record_dir}/{record['uuid']}/mask.png",
                    "user_report_link": record["user_report_link"],
                    "user_report_text": record["user_report_text"],
                    "relation_type": record["relation_type"],  # 1: 내가 검증, 2: 내 이미지가 검증됨, 3: 둘 다
                    "original_image_owner_id": record["original_image_owner_id"],
                    "original_image_filename": record["original_image_filename"],
                    "original_image_copyright": record["original_image_copyright"]
                }
                validation_records.append(record_data)
            
            # relation_type별로 분류
            all_records_list = []  # 전체보기
            my_validations_list = []  # 내가 검증한 것만 (relation_type 1)
            my_image_validations_list = []  # 다른사람이 내 이미지 검증한 것 (relation_type 2)
            self_validations_list = []  # 내가 검증했고 이미지도 내거 (relation_type 3)
            
            for record_data in validation_records:
                all_records_list.append(record_data)
                
                if record_data["relation_type"] == 1:
                    my_validations_list.append(record_data)
                elif record_data["relation_type"] == 2:
                    my_image_validations_list.append(record_data)
                elif record_data["relation_type"] == 3:
                    self_validations_list.append(record_data)
            
            # 요약 정보 구성
            summary_data = {
                "user_statistics": {
                    "my_validations_count": my_validations_count,  # 내가 검증한 것 (relation_type 1)
                    "my_image_validations_count": my_image_validations_count,  # 내 이미지가 검증된 것 (relation_type 2)  
                    "self_validations_count": self_validations_count,  # 내가 내 이미지를 검증한 것 (relation_type 3)
                    "total_records_count": total_records_count,
                    "returned_records_count": len(validation_records)
                },
                "validation_lists": {
                    "all": {
                        "name": "전체보기",
                        "count": len(all_records_list),
                        "records": all_records_list
                    },
                    "my_validations": {
                        "name": "내가 검증한 내역",
                        "count": len(my_validations_list),
                        "records": my_validations_list
                    },
                    "my_image_validations": {
                        "name": "타인이 검증한 내 이미지 내역",
                        "count": len(my_image_validations_list),
                        "records": my_image_validations_list
                    },
                    "self_validations": {
                        "name": "내가 검증한 내 이미지 내역",
                        "count": len(self_validations_list),
                        "records": self_validations_list
                    }
                },
                "relation_types": {
                    "1": "내가 검증한 데이터",
                    "2": "내 이미지가 검증된 데이터", 
                    "3": "내가 검증했고 대상도 내 이미지인 데이터"
                }
            }
            
            logger.info(f"Retrieved integrated validation summary for user {user_id}: {len(validation_records)} records")
            
            return BaseResponse(
                success=True,
                description="통합 검증 요약 정보를 조회했습니다.",
                data=[summary_data]
            )
            
        except Exception as e:
            logger.error(f"Failed to retrieve integrated validation summary for user {user_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"통합 검증 요약 정보 조회 중 오류가 발생했습니다: {str(e)}"
            )

    async def get_weekly_statistics(self, user_id: int, start_date: str, end_date: str) -> dict:
        """주간 통계 데이터 수집"""
        try:
            from datetime import datetime
            from app.models import Image
            
            start_dt = datetime.fromisoformat(start_date)
            end_dt = datetime.fromisoformat(end_date)
            
            # 1. 기본 통계 (지난 주 데이터)
            # 내가 검증한 레코드들
            my_validation_query = (
                ValidationRecord.__table__.select()
                .where(
                    sqlalchemy.and_(
                        ValidationRecord.user_id == user_id,
                        ValidationRecord.time_created >= start_dt,
                        ValidationRecord.time_created <= end_dt
                    )
                )
            )
            my_validation_records = await database.fetch_all(my_validation_query)
            
            # 내 이미지가 검증된 레코드들
            my_image_validation_query = (
                ValidationRecord.__table__.select()
                .select_from(
                    ValidationRecord.__table__.join(
                        Image.__table__, 
                        ValidationRecord.detected_watermark_image_id == Image.id
                    )
                )
                .where(
                    sqlalchemy.and_(
                        Image.user_id == user_id,
                        ValidationRecord.user_id != user_id,
                        ValidationRecord.time_created >= start_dt,
                        ValidationRecord.time_created <= end_dt
                    )
                )
            )
            my_image_validation_records = await database.fetch_all(my_image_validation_query)
            
            # 2. 위변조 검출 통계
            forgery_detected_count = 0
            total_validations = 0
            self_validations_count = 0
            forgery_reports = []  # 위변조 검출된 레포트 정보
            
            for record in my_validation_records:
                total_validations += 1
                if record["has_watermark"] and record["modification_rate"] and record["modification_rate"] > 0:
                    forgery_detected_count += 1
                    forgery_reports.append({
                        "validation_uuid": record["uuid"],
                        "filename": record["input_image_filename"],
                        "modification_rate": record["modification_rate"],
                        "validation_time": record["time_created"].strftime("%Y-%m-%d %H:%M")
                    })
                
                # 내가 검증했고 내 이미지인 경우
                if record["detected_watermark_image_id"]:
                    image_query = (
                        Image.__table__.select()
                        .where(Image.id == record["detected_watermark_image_id"])
                    )
                    image_record = await database.fetch_one(image_query)
                    if image_record and image_record["user_id"] == user_id:
                        self_validations_count += 1
            
            for record in my_image_validation_records:
                if record["has_watermark"] and record["modification_rate"] and record["modification_rate"] > 0:
                    forgery_detected_count += 1
                    forgery_reports.append({
                        "validation_uuid": record["uuid"],
                        "filename": record["input_image_filename"],
                        "modification_rate": record["modification_rate"],
                        "validation_time": record["time_created"].strftime("%Y-%m-%d %H:%M")
                    })
            
            # 최다 5개로 제한 (이메일 길이 제한)
            # forgery_reports = forgery_reports[:5]
            
            # 위변조 검출율 계산
            total_all_validations = total_validations + len(my_image_validation_records)
            forgery_detection_rate = (forgery_detected_count / total_all_validations * 100) if total_all_validations > 0 else 0.0
            
            statistics = {
                "my_validations_count": len(my_validation_records),
                "my_image_validations_count": len(my_image_validation_records),
                "self_validations_count": self_validations_count,
                "total_validations_count": total_all_validations,
                "forgery_detected_count": forgery_detected_count,
                "forgery_detection_rate": forgery_detection_rate,
                "forgery_reports": forgery_reports
            }
            
            return statistics
            
        except Exception as e:
            logger.error(f"Failed to get weekly statistics for user {user_id}: {str(e)}")
            return {}

    async def send_weekly_reports_to_all_users(self) -> dict:
        """모든 사용자에게 주간 리포트 발송"""
        from datetime import datetime, timedelta
        from app.models import User
        from app.services.email_service import email_service
        
        try:
            # 오늘부터 7일 전까지 계산
            today = datetime.now().date()
            week_end = today  # 오늘
            week_start = today - timedelta(days=6)  # 7일 전 (오늘 포함 7일)
            
            period_start = week_start.strftime('%Y-%m-%d')
            period_end = week_end.strftime('%Y-%m-%d')
            
            logger.info(f"Sending weekly reports for period: {period_start} ~ {period_end}")
            
            # 모든 사용자 조회
            users_query = User.__table__.select()
            users = await database.fetch_all(users_query)
            
            success_count = 0
            error_count = 0
            
            for user in users:
                try:
                    # 사용자별 주간 통계 수집
                    statistics = await self.get_weekly_statistics(
                        user["id"], 
                        f"{period_start} 00:00:00",
                        f"{period_end} 23:59:59"
                    )
                    
                    # 활동이 있는 사용자만 이메일 발송
                    if statistics.get("total_validations_count", 0) > 0:
                        success = await email_service.send_weekly_statistics_email(
                            user_email=user["email"],
                            username=user["name"],
                            statistics=statistics,
                            period_start=period_start,
                            period_end=period_end
                        )
                        
                        if success:
                            success_count += 1
                            logger.info(f"Weekly report sent successfully to {user['email']}")
                        else:
                            error_count += 1
                            logger.error(f"Failed to send weekly report to {user['email']}")
                    else:
                        logger.info(f"No activity for user {user['email']}, skipping email")
                        
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error processing weekly report for user {user['email']}: {str(e)}")
            
            result = {
                "success_count": success_count,
                "error_count": error_count,
                "total_users": len(users),
                "period_start": period_start,
                "period_end": period_end
            }
            
            logger.info(f"Weekly report batch completed: {success_count} success, {error_count} errors")
            return result
            
        except Exception as e:
            logger.error(f"Failed to send weekly reports: {str(e)}")
            return {
                "success_count": 0,
                "error_count": 0,
                "total_users": 0,
                "error": str(e)
            }

    async def send_individual_weekly_report(self, access_token: str) -> BaseResponse:
        """개인 주간 리포트 이메일 발송"""
        user_id = self.auth_service.get_user_id_from_token(access_token)
        
        try:
            from datetime import datetime, timedelta
            from app.models import User
            from app.services.email_service import email_service
            
            # 사용자 정보 조회
            user_query = User.__table__.select().where(User.id == int(user_id))
            user = await database.fetch_one(user_query)
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="사용자를 찾을 수 없습니다."
                )
            
            # 오늘부터 7일 전까지 계산
            today = datetime.now().date()
            week_end = today  # 오늘
            week_start = today - timedelta(days=6)  # 7일 전 (오늘 포함 7일)
            
            period_start = week_start.strftime('%Y-%m-%d')
            period_end = week_end.strftime('%Y-%m-%d')
            
            logger.info(f"Sending individual weekly report to user {user_id} for period: {period_start} ~ {period_end}")
            
            # 개인 주간 통계 수집
            statistics = await self.get_weekly_statistics(
                int(user_id), 
                f"{period_start} 00:00:00",
                f"{period_end} 23:59:59"
            )
            
            # 이메일 발송
            success = await email_service.send_weekly_statistics_email(
                user_email=user["email"],
                username=user["name"],
                statistics=statistics,
                period_start=period_start,
                period_end=period_end
            )
            
            if success:
                logger.info(f"Individual weekly report sent successfully to user {user_id}")
                return BaseResponse(
                    success=True,
                    description="주간 리포트가 이메일로 발송되었습니다.",
                    data=[{
                        "period_start": period_start,
                        "period_end": period_end,
                        "email": user["email"],
                        "statistics": statistics
                    }]
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="이메일 발송에 실패했습니다."
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to send individual weekly report to user {user_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"주간 리포트 발송 중 오류가 발생했습니다: {str(e)}"
            )

    async def send_custom_period_report(self, access_token: str, start_date: str, end_date: str) -> BaseResponse:
        """지정 기간 개인 리포트 이메일 발송"""
        user_id = self.auth_service.get_user_id_from_token(access_token)
        
        try:
            from datetime import datetime, timedelta
            from app.models import User
            from app.services.email_service import email_service
            
            # 날짜 형식 검증 및 변환
            try:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식을 사용해주세요."
                )
            
            # 날짜 유효성 검증
            if start_dt > end_dt:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="시작 날짜는 종료 날짜보다 이전이어야 합니다."
                )
            
            # 최대 90일 제한
            if (end_dt - start_dt).days > 90:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="조회 기간은 최대 90일까지 가능합니다."
                )
            
            # 미래 날짜 제한
            today = datetime.now().date()
            if end_dt > today:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="종료 날짜는 오늘 이전이어야 합니다."
                )
            
            # 사용자 정보 조회
            user_query = User.__table__.select().where(User.id == int(user_id))
            user = await database.fetch_one(user_query)
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="사용자를 찾을 수 없습니다."
                )
            
            logger.info(f"Sending custom period report to user {user_id} for period: {start_date} ~ {end_date}")
            
            # 지정 기간 통계 수집
            statistics = await self.get_weekly_statistics(
                int(user_id), 
                f"{start_date} 00:00:00",
                f"{end_date} 23:59:59"
            )
            
            # 활동이 없으면 알림
            if statistics.get("total_validations_count", 0) == 0:
                return BaseResponse(
                    success=True,
                    description="해당 기간에 활동 내역이 없어 리포트를 발송하지 않았습니다.",
                    data=[{
                        "period_start": start_date,
                        "period_end": end_date,
                        "email": user["email"],
                        "total_validations": 0,
                        "sent": False
                    }]
                )
            
            # 이메일 발송 (기간 리포트용으로 수정된 제목)
            success = await email_service.send_custom_period_statistics_email(
                user_email=user["email"],
                username=user["name"],
                statistics=statistics,
                period_start=start_date,
                period_end=end_date
            )
            
            if success:
                logger.info(f"Custom period report sent successfully to user {user_id}")
                return BaseResponse(
                    success=True,
                    description=f"{start_date}부터 {end_date}까지의 리포트가 이메일로 발송되었습니다.",
                    data=[{
                        "period_start": start_date,
                        "period_end": end_date,
                        "email": user["email"],
                        "statistics": statistics,
                        "sent": True
                    }]
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="이메일 발송에 실패했습니다."
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to send custom period report to user {user_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"기간 리포트 발송 중 오류가 발생했습니다: {str(e)}"
            )

    async def get_validation_raw_data(self, access_token: str, period: str = "7days") -> BaseResponse:
        """원시 검증 데이터 조회 - 프론트엔드에서 직접 분석할 수 있도록 단순한 형태로 제공"""
        user_id = self.auth_service.get_user_id_from_token(access_token)
        
        try:
            from datetime import datetime, timedelta
            from app.models import Image
            
            # 기간 설정
            now = datetime.now()
            if period == "1day":
                start_date = now - timedelta(days=1)
            elif period == "7days":
                start_date = now - timedelta(days=7)
            elif period == "30days":
                start_date = now - timedelta(days=30)
            else:  # "all"
                start_date = datetime(2020, 1, 1)  # 프로젝트 시작 기준
            
            # 모든 관련 검증 데이터 수집
            all_validations = []
            
            # 1. 내가 검증한 데이터
            my_validations_query = sqlalchemy.select(
                ValidationRecord.has_watermark,
                ValidationRecord.modification_rate,
                ValidationRecord.time_created
            ).select_from(ValidationRecord).where(
                sqlalchemy.and_(
                    ValidationRecord.user_id == int(user_id),
                    ValidationRecord.time_created >= start_date,
                    ValidationRecord.time_created <= now
                )
            ).order_by(ValidationRecord.time_created.desc())
            
            my_validations = await database.fetch_all(my_validations_query)
            
            # 2. 내 이미지가 다른 사람에 의해 검증된 데이터
            others_validations_query = sqlalchemy.select(
                ValidationRecord.has_watermark,
                ValidationRecord.modification_rate,
                ValidationRecord.time_created
            ).select_from(
                ValidationRecord.__table__.join(
                    Image.__table__, 
                    ValidationRecord.detected_watermark_image_id == Image.id
                )
            ).where(
                sqlalchemy.and_(
                    Image.user_id == int(user_id),
                    ValidationRecord.user_id != int(user_id),
                    ValidationRecord.time_created >= start_date,
                    ValidationRecord.time_created <= now
                )
            ).order_by(ValidationRecord.time_created.desc())
            
            others_validations = await database.fetch_all(others_validations_query)
            
            # 모든 검증 데이터를 단순한 형태로 변환
            for validation in my_validations:
                all_validations.append({
                    "is_tampered": bool(getattr(validation, 'has_watermark', False) and 
                                     getattr(validation, 'modification_rate', 0) and 
                                     getattr(validation, 'modification_rate', 0) > 0),
                    "validation_time": getattr(validation, 'time_created').isoformat()
                })
            
            for validation in others_validations:
                all_validations.append({
                    "is_tampered": bool(getattr(validation, 'has_watermark', False) and 
                                     getattr(validation, 'modification_rate', 0) and 
                                     getattr(validation, 'modification_rate', 0) > 0),
                    "validation_time": getattr(validation, 'time_created').isoformat()
                })
            
            # 시간순으로 정렬 (최신순)
            all_validations.sort(key=lambda x: x['validation_time'], reverse=True)
            
            logger.info(f"Retrieved {len(all_validations)} raw validation records for user {user_id} (period: {period})")
            
            return BaseResponse(
                success=True,
                description="검증 데이터 조회 완료",
                data=[{
                    "period": period,
                    "validations": all_validations
                }]
            )
            
        except Exception as e:
            logger.error(f"Failed to get validation raw data for user {user_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"검증 데이터 조회 중 오류가 발생했습니다: {str(e)}"
            )

    async def get_dashboard_statistics(self, period: str = "7days"):
        """대시보드용 통계 데이터 수집"""
        try:
            from datetime import datetime, timedelta
            
            # 기간 설정
            now = datetime.now()
            if period == "1day":
                start_date = now - timedelta(days=1)
                prev_start = start_date - timedelta(days=1)
                prev_end = start_date
            elif period == "7days":
                start_date = now - timedelta(days=7)
                prev_start = start_date - timedelta(days=7)
                prev_end = start_date
            elif period == "30days":
                start_date = now - timedelta(days=30)
                prev_start = start_date - timedelta(days=30)
                prev_end = start_date
            else:  # "all"
                start_date = datetime(2020, 1, 1)  # 프로젝트 시작 기준
                prev_start = start_date
                prev_end = now - timedelta(days=365)  # 작년 같은 기간
            
            # 1. 현재 기간 요약 통계
            current_validations_query = sqlalchemy.select(
                sqlalchemy.func.count().label('total_validations'),
                sqlalchemy.func.sum(
                    sqlalchemy.case((ValidationRecord.has_watermark == True, 1), else_=0)
                ).label('total_forgeries')
            ).select_from(ValidationRecord).where(
                sqlalchemy.and_(
                    ValidationRecord.time_created >= start_date,
                    ValidationRecord.time_created <= now
                )
            )
            
            current_stats = await database.fetch_one(current_validations_query)
            
            # 2. 이전 기간 통계 (비교용)
            prev_validations_query = sqlalchemy.select(
                sqlalchemy.func.count().label('total_validations'),
                sqlalchemy.func.sum(
                    sqlalchemy.case((ValidationRecord.has_watermark == True, 1), else_=0)
                ).label('total_forgeries')
            ).select_from(ValidationRecord).where(
                sqlalchemy.and_(
                    ValidationRecord.time_created >= prev_start,
                    ValidationRecord.time_created <= prev_end
                )
            )
            
            prev_stats = await database.fetch_one(prev_validations_query)
            
            # 3. 활성 사용자 수
            active_users_query = sqlalchemy.select(
                sqlalchemy.func.count(sqlalchemy.distinct(ValidationRecord.user_id)).label('active_users')
            ).select_from(ValidationRecord).where(
                sqlalchemy.and_(
                    ValidationRecord.time_created >= start_date,
                    ValidationRecord.time_created <= now
                )
            )
            
            active_users_result = await database.fetch_one(active_users_query)
            
            # 4. 총 이미지 수
            from app.models import Image
            total_images_query = sqlalchemy.select(sqlalchemy.func.count().label('total_images')).select_from(Image)
            total_images_result = await database.fetch_one(total_images_query)
            
            # 5. 일별 데이터 (최근 기간만)
            if period == "all":
                # 전체 기간일 때는 월별 데이터
                daily_query = sqlalchemy.select(
                    sqlalchemy.func.date_format(ValidationRecord.time_created, '%Y-%m').label('date'),
                    sqlalchemy.func.count().label('validations'),
                    sqlalchemy.func.sum(
                        sqlalchemy.case((ValidationRecord.has_watermark == True, 1), else_=0)
                    ).label('forgeries'),
                    sqlalchemy.func.count(sqlalchemy.distinct(ValidationRecord.user_id)).label('active_users')
                ).select_from(ValidationRecord).where(
                    ValidationRecord.time_created >= start_date
                ).group_by(
                    sqlalchemy.func.date_format(ValidationRecord.time_created, '%Y-%m')
                ).order_by(
                    sqlalchemy.desc(sqlalchemy.func.date_format(ValidationRecord.time_created, '%Y-%m'))
                ).limit(12)
            else:
                # 일별 데이터
                daily_query = sqlalchemy.select(
                    sqlalchemy.func.date(ValidationRecord.time_created).label('date'),
                    sqlalchemy.func.count().label('validations'),
                    sqlalchemy.func.sum(
                        sqlalchemy.case((ValidationRecord.has_watermark == True, 1), else_=0)
                    ).label('forgeries'),
                    sqlalchemy.func.count(sqlalchemy.distinct(ValidationRecord.user_id)).label('active_users')
                ).select_from(ValidationRecord).where(
                    sqlalchemy.and_(
                        ValidationRecord.time_created >= start_date,
                        ValidationRecord.time_created <= now
                    )
                ).group_by(
                    sqlalchemy.func.date(ValidationRecord.time_created)
                ).order_by(
                    sqlalchemy.desc(sqlalchemy.func.date(ValidationRecord.time_created))
                )
                
            daily_data = await database.fetch_all(daily_query)
            
            # 6. 통계 계산
            total_validations = getattr(current_stats, 'total_validations', 0) or 0
            total_forgeries = getattr(current_stats, 'total_forgeries', 0) or 0
            detection_rate = (total_forgeries / total_validations * 100) if total_validations > 0 else 0
            
            prev_validations = getattr(prev_stats, 'total_validations', 0) or 0
            prev_forgeries = getattr(prev_stats, 'total_forgeries', 0) or 0
            
            validation_growth = ((total_validations - prev_validations) / prev_validations * 100) if prev_validations > 0 else 0
            forgery_growth = ((total_forgeries - prev_forgeries) / prev_forgeries * 100) if prev_forgeries > 0 else 0
            
            # 7. 응답 데이터 구성
            from app.schemas import DashboardStats, DashboardSummary, DailyStat, PeriodComparison
            
            summary = DashboardSummary(
                total_validations=total_validations,
                total_forgeries=total_forgeries,
                detection_rate=round(detection_rate, 2),
                active_users=getattr(active_users_result, 'active_users', 0) or 0,
                total_images=getattr(total_images_result, 'total_images', 0) or 0
            )
            
            daily_stats = [
                DailyStat(
                    date=str(getattr(row, 'date', '')),
                    validations=getattr(row, 'validations', 0),
                    forgeries=getattr(row, 'forgeries', 0) or 0,
                    active_users=getattr(row, 'active_users', 0)
                )
                for row in daily_data
            ]
            
            comparison = PeriodComparison(
                current_validations=total_validations,
                current_forgeries=total_forgeries,
                previous_validations=prev_validations,
                previous_forgeries=prev_forgeries,
                validation_growth_rate=round(validation_growth, 2),
                forgery_growth_rate=round(forgery_growth, 2)
            )
            
            dashboard_stats = DashboardStats(
                period=period,
                summary=summary,
                daily_data=daily_stats,
                comparison=comparison
            )
            
            logger.info(f"Dashboard statistics generated for period {period}: {total_validations} validations, {total_forgeries} forgeries")
            return dashboard_stats
            
        except Exception as e:
            logger.error(f"Failed to get dashboard statistics for period {period}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"대시보드 통계 조회 중 오류가 발생했습니다: {str(e)}"
            )


    async def get_user_report_statistics(self, access_token: str) -> BaseResponse:
        """내 유저 제보 데이터 통계 조회"""
        try:
            import re
            from collections import Counter
            
            # 토큰에서 사용자 ID 추출
            user_id = self.auth_service.get_user_id_from_token(access_token)
            
            # 내 원본 이미지에 대한 모든 제보 데이터 조회 (본인 + 다른 사람 제보)
            # ValidationRecord와 Image를 JOIN하여 내가 원본 소유자인 검증 기록 조회
            query = sqlalchemy.select(
                ValidationRecord.user_report_link,
                ValidationRecord.time_created
            ).select_from(
                ValidationRecord.__table__.join(
                    Image.__table__, 
                    ValidationRecord.detected_watermark_image_id == Image.id
                )
            ).where(
                sqlalchemy.and_(
                    Image.user_id == int(user_id),  # 내가 원본 이미지 소유자
                    ValidationRecord.user_report_link.isnot(None),
                    ValidationRecord.user_report_link != ""
                )
            ).order_by(ValidationRecord.time_created.desc())
            
            records = await database.fetch_all(query)
            
            if not records:
                from app.schemas import UserReportStats, DomainFrequency, RecentReportLink
                empty_stats = UserReportStats(
                    most_frequent_domains=[],
                    recent_report_links=[]
                )
                return BaseResponse(
                    success=True,
                    description="내 제보 데이터가 없습니다.",
                    data=[empty_stats.model_dump()]
                )
            
            # URL에서 도메인 추출 및 빈도 계산
            domains = []
            recent_links = []
            
            for record in records:
                link = getattr(record, 'user_report_link', None)
                if not link:
                    continue
                
                # 최근 5개 링크 수집
                if len(recent_links) < 5:
                    recent_links.append({
                        'link': link,
                        'reported_time': getattr(record, 'time_created').isoformat()
                    })
                
                # 도메인 추출
                try:
                    # URL에서 프로토콜과 경로 제거, 도메인만 추출
                    # https:// 또는 http:// 제거
                    cleaned_url = re.sub(r'^https?://', '', link)
                    # 경로와 쿼리 파라미터 제거
                    domain = cleaned_url.split('/')[0].split('?')[0].split('#')[0]
                    # www. 제거
                    domain = re.sub(r'^www\.', '', domain)
                    
                    if domain:  # 빈 문자열이 아닌 경우만
                        domains.append(domain)
                
                except Exception as e:
                    logger.warning(f"도메인 추출 실패: {link}, 오류: {str(e)}")
                    continue
            
            # 도메인 빈도수 계산 (상위 5개)
            domain_counter = Counter(domains)
            top_domains = domain_counter.most_common(5)
            
            from app.schemas import UserReportStats, DomainFrequency, RecentReportLink
            
            # 응답 데이터 구성
            most_frequent_domains = [
                DomainFrequency(domain=domain, count=count) 
                for domain, count in top_domains
            ]
            
            recent_report_links = [
                RecentReportLink(link=item['link'], reported_time=item['reported_time']) 
                for item in recent_links
            ]
            
            stats = UserReportStats(
                most_frequent_domains=most_frequent_domains,
                recent_report_links=recent_report_links
            )
            
            logger.info(f"User report statistics generated: {len(most_frequent_domains)} domains, {len(recent_report_links)} recent links")
            
            return BaseResponse(
                success=True,
                description="내 유저 제보 통계를 조회했습니다.",
                data=[stats.model_dump()]
            )
            
        except Exception as e:
            logger.error(f"Failed to get user report statistics: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"유저 제보 통계 조회 중 오류가 발생했습니다: {str(e)}"
            )


validation_service = ValidationService()
