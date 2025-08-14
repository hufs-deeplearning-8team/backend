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
        
        # 알고리즘별로 다른 결과 시뮬레이션
        if algorithm == "EditGuard":
            has_watermark = random.choice([True, True, False])  # 높은 감지율
        elif algorithm == "OmniGuard":
            has_watermark = random.choice([True, False, False])  # 중간 감지율
        else:  # RobustWide
            has_watermark = random.choice([True, False])  # 기본 감지율
        
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
                
                # RobustWide 모델 특별 처리: 픽셀 비교 기반 마스크 생성
                if validation_enum == ProtectionAlgorithm.RobustWide:
                    await self._process_robustwide_validation(
                        contents, original_image_id, verification_result
                    )
            else:
                # original_image_id가 없는 경우 처리
                logger.info(f"original_image_id가 없습니다: {original_image_id}")
                
                # RobustWide의 경우 워터마크가 감지되지 않더라도 처리할 수 있도록 대안 로직 추가
                if validation_enum == ProtectionAlgorithm.RobustWide:
                    logger.info("RobustWide: original_image_id 없음. AI 서버 응답 기반으로 처리합니다.")
                    # AI 서버에서 받은 기본 변조률과 mask 사용
                    # (실제 프로덕션에서는 다른 로직 구현 가능)

            # AI 응답을 AIValidationResponse 형식으로 변환
            calculated_rate = verification_result.get("tampering_rate", 0)
            mask_data = verification_result.get("tampered_regions_mask", "")
            
            ai_response = AIValidationResponse(
                has_watermark=calculated_rate > 0,
                detected_watermark_image_id=original_image_id,
                modification_rate=calculated_rate,
                visualization_image_base64=mask_data
            )
            
            
            logger.info(f"AI validation result: watermark={ai_response.has_watermark}, modification_rate={ai_response.modification_rate}, detected_id={ai_response.detected_watermark_image_id}")
            
            # ValidationRecord에 결과 저장
            validation_uuid = str(uuid.uuid4())
            
            query = sqlalchemy.insert(ValidationRecord).values(
                uuid=validation_uuid,
                user_id=int(user_id),
                input_image_filename=original_filename,
                has_watermark=ai_response.has_watermark,
                detected_watermark_image_id=ai_response.detected_watermark_image_id,
                modification_rate=ai_response.modification_rate,
                validation_algorithm=validation_enum
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
                    
                    # 사용된 알고리즘에 따라 로그 메시지 구분
                    if validation_enum == ProtectionAlgorithm.RobustWide:
                        logger.info(f"RobustWide generated mask image saved to S3: {mask_s3_path}")
                    else:
                        logger.info(f"AI server mask image saved to S3: {mask_s3_path}")
                    
                    # 원본 이미지와 mask를 합성한 이미지 생성
                    try:
                        combined_bytes = self._create_combined_image(contents, mask_bytes)
                        combined_s3_path = f"record/{validation_uuid}/combined.png"
                        await self.storage_service.upload_file(combined_bytes, combined_s3_path)
                        logger.info(f"Combined image saved to S3: {combined_s3_path}")
                    except Exception as combine_error:
                        logger.error(f"Failed to create combined image: {str(combine_error)}")
                else:
                    # mask가 없는 경우 (변조되지 않은 경우)
                    if validation_enum == ProtectionAlgorithm.RobustWide:
                        logger.info(f"RobustWide: No tampering detected, no mask generated")
                    else:
                        logger.info(f"AI server: No mask data provided")
                    
            except Exception as s3_error:
                logger.error(f"Failed to save validation images to S3: {str(s3_error)}")
                # S3 저장 실패해도 검증은 계속 진행
            
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
    
    # RobustWide mask 생성 관련 상수
    PIXEL_DIFF_THRESHOLD = 10  # RGB 값 차이 임계값
    TAMPERED_COLOR = [255, 255, 255, 255]  # 하얀색, 불투명
    NORMAL_COLOR = [0, 0, 0, 0]  # 투명
    
    async def _create_difference_mask(self, input_image_bytes: bytes, original_sr_h_bytes: bytes) -> tuple[str, float]:
        """
        RobustWide용 픽셀 차이 기반 마스크 생성
        
        Args:
            input_image_bytes: 검증할 입력 이미지 바이트
            original_sr_h_bytes: 원본 sr_h 이미지 바이트
            
        Returns:
            tuple[str, float]: (base64 인코딩된 마스크 이미지, 변조률)
        """
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
            
            logger.info(f"RobustWide mask 생성 완료: 변조률 {tampering_rate:.2f}% "
                       f"({np.sum(tampered_mask)}/{tampered_mask.size} 픽셀)")
            
            return mask_base64, tampering_rate
            
        except Exception as e:
            logger.error(f"RobustWide mask 생성 중 오류: {str(e)}")
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
    
    async def _process_robustwide_validation(self, input_image_bytes: bytes, original_image_id: int, verification_result: dict) -> None:
        """
        RobustWide 모델 검증 처리
        
        Args:
            input_image_bytes: 입력 이미지 바이트
            original_image_id: 원본 이미지 ID
            verification_result: 검증 결과 딕셔너리 (수정됨)
        """
        try:
            # 원본 sr_h 이미지 다운로드
            original_sr_h_path = f"image/{original_image_id}/sr_h.png"
            original_sr_h_bytes = await self.storage_service.download_file(original_sr_h_path)
            
            # 픽셀 비교 기반 마스크 및 변조률 생성
            mask_data, tampering_rate = await self._create_difference_mask(
                input_image_bytes, original_sr_h_bytes
            )
            
            # 결과 업데이트
            self._update_verification_result(verification_result, mask_data, tampering_rate, original_image_id)
            
        except Exception as error:
            logger.warning(f"RobustWide 검증 처리 중 오류: {str(error)}. 기존 AI 서버 결과 유지")
            # 오류 발생 시 기존 AI 서버 결과 그대로 사용
    
    def _update_verification_result(self, verification_result: dict, mask_data: str, tampering_rate: float, original_image_id: int) -> None:
        """검증 결과 업데이트"""
        if tampering_rate == 0.0:
            logger.info(f"RobustWide: 입력 이미지와 원본 이미지(ID: {original_image_id}) 일치 - 변조 없음")
            verification_result.update({
                "tampering_rate": 0.0,
                "tampered_regions_mask": ""
            })
        else:
            logger.info(f"RobustWide: 변조 감지 - 변조률: {tampering_rate:.2f}% (원본 ID: {original_image_id})")
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


validation_service = ValidationService()