import base64
import io
import logging
import random
from datetime import datetime
from typing import Dict, List

import numpy as np
from fastapi import HTTPException, status, UploadFile
import sqlalchemy
from PIL import Image as PILImage

from app.config import settings
from app.db import database
from app.models import Image, ProtectionAlgorithm, User
from app.schemas import BaseResponse
from app.services.auth_service import auth_service
from app.services.storage_service import storage_service
from app.services.email_service import email_service

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
    
    async def upload_image(self, file: UploadFile, copyright: str, protection_algorithm: str, access_token: str) -> BaseResponse:
        """이미지 업로드 처리"""
        user_id = self.auth_service.get_user_id_from_token(access_token)
        self.validate_file(file)
        
        # protection_algorithm 검증
        try:
            protection_enum = ProtectionAlgorithm(protection_algorithm)
        except ValueError:
            valid_algorithms = [alg.value for alg in ProtectionAlgorithm]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"유효하지 않은 보호 알고리즘입니다. 사용 가능한 값: {valid_algorithms}"
            )
        
        # 파일명 정리
        original_filename = self.clean_filename(file.filename)
        logger.info(f"Original filename: {file.filename} -> Cleaned: {original_filename}")
        
        # 파일 내용 읽기
        file_content = await file.read()
        
        # 트랜잭션으로 전체 과정 처리
        async with database.transaction():
            # 1. DB에 이미지 정보 저장 (트랜잭션 내부)
            from app.models import kst_now
            
            query = (
                sqlalchemy.insert(Image)
                .values(
                    user_id=int(user_id), 
                    copyright=copyright, 
                    filename=original_filename,
                    protection_algorithm=protection_enum,
                    use_openapi=False,
                    time_created=kst_now()
                )
                .returning(Image)
            )
            
            result = await database.fetch_one(query)
            inserted_data = dict(result)
            image_id = inserted_data["id"]

            logger.info(f"Image uploaded to DB: {inserted_data}")
            
            try:
                # 2. AI 서버 요청
                watermarked_image_content = await self._send_to_ai_server(file_content, image_id, protection_enum)
                
                # 3. S3에 원본(GT)과 워터마크(SRH) 이미지 업로드
                # 파일명에서 확장자 제거
                filename_without_ext = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
                gt_path = f"image/{image_id}/{filename_without_ext}_origi.png"
                srh_path = f"image/{image_id}/{filename_without_ext}_wm.png"
                
                # S3 업로드 중 하나라도 실패하면 업로드된 파일들을 정리
                uploaded_files = []
                try:
                    await self.storage_service.upload_file(file_content, gt_path)
                    uploaded_files.append(gt_path)
                    
                    await self.storage_service.upload_file(watermarked_image_content, srh_path)
                    uploaded_files.append(srh_path)
                    
                    logger.info(f"Files uploaded to S3: GT={gt_path}, SRH={srh_path}")
                    
                except Exception as s3_error:
                    # 업로드 실패시 이미 업로드된 파일들 정리
                    logger.error(f"S3 업로드 실패, 업로드된 파일 정리: {uploaded_files}")
                    await self.storage_service.delete_multiple_files(uploaded_files)
                    raise s3_error
                
            except Exception as e:
                # AI 서버 또는 S3 업로드 실패 시 트랜잭션이 자동 롤백됨
                logger.error(f"AI 서버 또는 S3 업로드 실패: {str(e)}")
                logger.info(f"Transaction rolled back for image_id: {image_id}")
                raise
        
        # 응답 데이터에 S3 URL 정보 추가
        response_data = dict(inserted_data)
        response_data["s3_paths"] = self.storage_service.get_image_urls(image_id, original_filename)
        
        return BaseResponse(
            success=True, 
            description="생성 성공", 
            data=[response_data]
        )
    
    async def upload_image_with_user_id(self, file: UploadFile, copyright: str, protection_algorithm: str, user_id: str) -> BaseResponse:
        """API 키를 통한 이미지 업로드 처리 (user_id 직접 전달)"""
        self.validate_file(file)
        
        # protection_algorithm 검증
        try:
            protection_enum = ProtectionAlgorithm(protection_algorithm)
        except ValueError:
            valid_algorithms = [alg.value for alg in ProtectionAlgorithm]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"유효하지 않은 보호 알고리즘입니다. 사용 가능한 값: {valid_algorithms}"
            )
        
        # 파일명 정리
        original_filename = self.clean_filename(file.filename)
        logger.info(f"Original filename: {file.filename} -> Cleaned: {original_filename}")
        
        # 파일 내용 읽기
        file_content = await file.read()
        
        # 트랜잭션으로 전체 과정 처리
        async with database.transaction():
            # 1. DB에 이미지 정보 저장 (트랜잭션 내부)
            from app.models import kst_now
            
            query = (
                sqlalchemy.insert(Image)
                .values(
                    user_id=int(user_id), 
                    copyright=copyright, 
                    filename=original_filename,
                    protection_algorithm=protection_enum,
                    use_openapi=True,
                    time_created=kst_now()
                )
                .returning(Image)
            )
            
            result = await database.fetch_one(query)
            inserted_data = dict(result)
            image_id = inserted_data["id"]

            logger.info(f"Image uploaded to DB via API key: {inserted_data}")
            
            try:
                # 2. AI 서버 요청
                watermarked_image_content = await self._send_to_ai_server(file_content, image_id, protection_enum)
                
                # 3. S3에 원본(GT)과 워터마크(SRH) 이미지 업로드
                # 파일명에서 확장자 제거
                filename_without_ext = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
                gt_path = f"image/{image_id}/{filename_without_ext}_origi.png"
                srh_path = f"image/{image_id}/{filename_without_ext}_wm.png"
                
                # S3 업로드 중 하나라도 실패하면 업로드된 파일들을 정리
                uploaded_files = []
                try:
                    await self.storage_service.upload_file(file_content, gt_path)
                    uploaded_files.append(gt_path)
                    
                    await self.storage_service.upload_file(watermarked_image_content, srh_path)
                    uploaded_files.append(srh_path)
                    
                    logger.info(f"Files uploaded to S3 via API key: GT={gt_path}, SRH={srh_path}")
                    
                except Exception as s3_error:
                    # 업로드 실패시 이미 업로드된 파일들 정리
                    logger.error(f"S3 업로드 실패, 업로드된 파일 정리: {uploaded_files}")
                    await self.storage_service.delete_multiple_files(uploaded_files)
                    raise s3_error
                
            except Exception as e:
                # AI 서버 또는 S3 업로드 실패 시 트랜잭션이 자동 롤백됨
                logger.error(f"AI 서버 또는 S3 업로드 실패: {str(e)}")
                logger.info(f"Transaction rolled back for image_id: {image_id}")
                raise
        
        # 응답 데이터에 S3 URL 정보 추가
        response_data = dict(inserted_data)
        response_data["s3_paths"] = self.storage_service.get_image_urls(image_id, original_filename)
        
        return BaseResponse(
            success=True, 
            description="API를 통한 생성 성공", 
            data=[response_data]
        )
    
    async def _send_to_ai_server(self, image_content: bytes, image_id: int, model: ProtectionAlgorithm) -> bytes:
        """AI 서버가 없는 환경에서 입력 이미지를 그대로 반환."""
        logger.info(
            "AI 서버가 비활성화되어 로컬에서 워터마크 이미지를 시뮬레이션합니다. "
            f"image_id={image_id}, algorithm={model.value}"
        )
        return image_content
        
    async def get_user_images(self, access_token: str, limit: int = 20, offset: int = 0) -> BaseResponse:
        """사용자가 업로드한 이미지 목록 조회"""
        user_id = self.auth_service.get_user_id_from_token(access_token)
        
        logger.info(f"User {user_id} requested their uploaded images (limit={limit}, offset={offset})")
        
        try:
            # 사용자가 업로드한 이미지 목록 조회
            query = (
                Image.__table__.select()
                .where(Image.user_id == int(user_id))
                .order_by(Image.id.desc())
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
                    "protection_algorithm": image["protection_algorithm"],
                    "upload_time": image["time_created"].isoformat(),
                    "s3_paths": self.storage_service.get_image_urls(image["id"], image["filename"])
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
    
    async def verify_image(self, file: UploadFile, model: str, access_token: str) -> BaseResponse:
        """이미지 위변조 검증"""
        user_id = self.auth_service.get_user_id_from_token(access_token)
        self.validate_file(file)
        
        # protection_algorithm 검증
        try:
            protection_enum = ProtectionAlgorithm(model)
        except ValueError:
            valid_algorithms = [alg.value for alg in ProtectionAlgorithm]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"유효하지 않은 보호 알고리즘입니다. 사용 가능한 값: {valid_algorithms}"
            )
        
        logger.info(f"User {user_id} requested image verification with model {model}")
        
        try:
            # 파일 내용 읽기
            file_content = await file.read()
            
            # AI 서버로 검증 요청
            verification_result = await self._send_to_ai_server_for_verification(file_content, protection_enum)
            
            # 검증에 성공한 경우 원본 이미지의 저작권 정보 추가
            original_image_id = verification_result.get("original_image_id")
            logger.info(f"검증 결과에서 추출된 original_image_id: {original_image_id}")
            if original_image_id:
                copyright_info = await self._get_original_image_copyright(original_image_id)
                verification_result["original_copyright"] = copyright_info
            else:
                logger.warning("original_image_id가 없어서 저작권 정보를 조회할 수 없습니다.")
                verification_result["original_copyright"] = {}
            
            # 위변조가 검출된 경우 원본 이미지 소유자에게 이메일 발송
            if verification_result.get("tampering_rate", 0) > 0:  # 변조가 검출되면 무조건 알림
                try:
                    await self._send_forgery_notification(verification_result, file.filename)
                except Exception as e:
                    logger.error(f"위변조 알림 이메일 발송 실패: {str(e)}")
            
            return BaseResponse(
                success=True,
                description="이미지 위변조 검증이 완료되었습니다.",
                data=[verification_result]
            )
            
        except Exception as e:
            logger.error(f"Image verification failed for user {user_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"이미지 검증 중 오류가 발생했습니다: {str(e)}"
            )
    
    async def verify_image_with_user_id(self, file: UploadFile, model: str, user_id: str) -> BaseResponse:
        """API 키를 통한 이미지 위변조 검증 (user_id 직접 전달)"""
        self.validate_file(file)
        
        # protection_algorithm 검증
        try:
            protection_enum = ProtectionAlgorithm(model)
        except ValueError:
            valid_algorithms = [alg.value for alg in ProtectionAlgorithm]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"유효하지 않은 보호 알고리즘입니다. 사용 가능한 값: {valid_algorithms}"
            )
        
        logger.info(f"User {user_id} requested image verification via API key with model {model}")
        
        try:
            # 파일 내용 읽기
            file_content = await file.read()
            
            # AI 서버로 검증 요청
            verification_result = await self._send_to_ai_server_for_verification(file_content, protection_enum)
            
            # 검증에 성공한 경우 원본 이미지의 저작권 정보 추가
            original_image_id = verification_result.get("original_image_id")
            logger.info(f"검증 결과에서 추출된 original_image_id: {original_image_id}")
            if original_image_id:
                copyright_info = await self._get_original_image_copyright(original_image_id)
                verification_result["original_copyright"] = copyright_info
            else:
                logger.warning("original_image_id가 없어서 저작권 정보를 조회할 수 없습니다.")
                verification_result["original_copyright"] = {}
            
            # OPENAPI에서는 이메일 발송 비활성화
            # if verification_result.get("tampering_rate", 0) > 0:  # 변조가 검출되면 무조건 알림
            #     try:
            #         await self._send_forgery_notification(verification_result, file.filename)
            #     except Exception as e:
            #         logger.error(f"위변조 알림 이메일 발송 실패: {str(e)}")
            
            return BaseResponse(
                success=True,
                description="API를 통한 이미지 위변조 검증이 완료되었습니다.",
                data=[verification_result]
            )
            
        except Exception as e:
            logger.error(f"Image verification via API key failed for user {user_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"이미지 검증 중 오류가 발생했습니다: {str(e)}"
            )
    
    def _generate_dummy_tampering_overlay(self, image_content: bytes) -> tuple[str, List[Dict[str, float]], float]:
        """입력 이미지를 기반으로 랜덤한 변조 영역 마스크와 메타데이터를 생성합니다."""
        width, height = 512, 512
        try:
            with PILImage.open(io.BytesIO(image_content)) as input_image:
                width, height = input_image.size
        except Exception as exc:
            logger.warning("입력 이미지 크기를 확인할 수 없어 기본 크기를 사용합니다: %s", str(exc))
        
        width = max(1, width)
        height = max(1, height)
        total_pixels = width * height
        mask = np.zeros((height, width), dtype=bool)
        min_dim = max(1, min(width, height))
        target_ratio = random.uniform(0.05, 0.35)
        target_pixels = max(1, int(total_pixels * target_ratio))
        max_regions = random.randint(1, 4)
        regions: List[Dict[str, float]] = []
        y_indices, x_indices = np.ogrid[:height, :width]
        attempts = 0
        
        while np.count_nonzero(mask) < target_pixels and len(regions) < max_regions and attempts < max_regions * 4:
            min_radius = max(4, int(min_dim * 0.05))
            max_radius = max(min_radius, int(min_dim * 0.25))
            radius = random.randint(min_radius, max_radius)
            center_x = random.randint(0, width - 1)
            center_y = random.randint(0, height - 1)
            
            circle_mask = (x_indices - center_x) ** 2 + (y_indices - center_y) ** 2 <= radius ** 2
            new_region = circle_mask & ~mask
            new_pixels = int(np.count_nonzero(new_region))
            attempts += 1
            if new_pixels == 0:
                continue
            
            mask[circle_mask] = True
            
            ys, xs = np.where(new_region)
            x1, x2 = int(xs.min()), int(xs.max())
            y1, y2 = int(ys.min()), int(ys.max())
            region_area = float(new_pixels)
            coverage = round(region_area / total_pixels * 100, 2)
            regions.append({
                "x": x1,
                "y": y1,
                "width": x2 - x1 + 1,
                "height": y2 - y1 + 1,
                "area": round(region_area, 2),
                "coverage": coverage,
                "confidence": round(random.uniform(0.65, 0.95), 2),
            })
        
        if not regions:
            # 최소 한 개의 변조 영역은 제공되도록 기본 원형 영역 생성
            radius = max(10, min_dim // 5)
            center_x = width // 2
            center_y = height // 2
            fallback_mask = (x_indices - center_x) ** 2 + (y_indices - center_y) ** 2 <= radius ** 2
            mask = fallback_mask
            ys, xs = np.where(fallback_mask)
            if ys.size and xs.size:
                x1, x2 = int(xs.min()), int(xs.max())
                y1, y2 = int(ys.min()), int(ys.max())
                region_area = float(np.count_nonzero(fallback_mask))
                coverage = round(region_area / total_pixels * 100, 2)
                regions.append({
                    "x": x1,
                    "y": y1,
                    "width": x2 - x1 + 1,
                    "height": y2 - y1 + 1,
                    "area": round(region_area, 2),
                    "coverage": coverage,
                    "confidence": round(random.uniform(0.7, 0.9), 2),
                })
        
        tampered_pixels = int(np.count_nonzero(mask))
        tampering_rate = round((tampered_pixels / total_pixels) * 100, 2) if total_pixels else 0.0
        if tampering_rate <= 0:
            tampering_rate = round(random.uniform(1.0, 5.0), 2)
        
        alpha_value = random.randint(140, 210)
        mask_rgba = np.zeros((height, width, 4), dtype=np.uint8)
        mask_rgba[..., 0] = 255
        mask_rgba[..., 1] = 0
        mask_rgba[..., 2] = 0
        mask_rgba[..., 3] = mask.astype(np.uint8) * alpha_value
        
        buffer = io.BytesIO()
        try:
            PILImage.fromarray(mask_rgba, mode="RGBA").save(buffer, format="PNG")
        except Exception as exc:
            logger.error("변조 마스크 이미지를 생성하지 못했습니다: %s", str(exc))
            return "", regions, tampering_rate
        
        mask_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return mask_base64, regions, tampering_rate
    
    async def _send_to_ai_server_for_verification(self, image_content: bytes, model: ProtectionAlgorithm) -> dict:
        """AI 서버가 없는 환경에서 위변조 검증 결과를 시뮬레이션합니다."""
        logger.info(
            "AI 서버가 비활성화되어 로컬에서 검증 결과를 생성합니다. "
            f"algorithm={model.value}"
        )

        has_watermark = random.choice([True, False])
        mask_data = ""
        tampered_regions: List[Dict[str, float]] = []
        tampering_rate = 0.0
        if has_watermark:
            mask_data, tampered_regions, tampering_rate = self._generate_dummy_tampering_overlay(image_content)
            if not mask_data:
                mask_data = base64.b64encode(image_content).decode("utf-8")
            if tampering_rate <= 0:
                tampering_rate = round(random.uniform(5.0, 15.0), 2)

        original_image_id = None
        if has_watermark:
            query = (
                sqlalchemy.select(Image.id)
                .order_by(Image.id.desc())
                .limit(1)
            )
            existing_image = await database.fetch_one(query)
            if existing_image:
                original_image_id = existing_image["id"]

        logger.info(
            "Dummy verification generated: has_watermark=%s, tampering_rate=%.2f, original_image_id=%s",
            has_watermark,
            tampering_rate,
            original_image_id,
        )

        result = {
            "ai_tampering_rate": tampering_rate,
            "tampering_rate": tampering_rate,
            "tampered_regions_mask": mask_data,
            "original_image_id": original_image_id,
        }
        if tampered_regions:
            result["tampered_regions"] = tampered_regions
        return result

    async def _send_forgery_notification(self, verification_result: dict, detected_filename: str) -> None:
        """위변조 검출시 원본 이미지 소유자에게 이메일 발송"""
        try:
            original_image_id = verification_result.get("original_image_id")
            if not original_image_id:
                logger.warning("원본 이미지 ID를 찾을 수 없어 알림 이메일을 발송하지 않습니다.")
                return
            
            # 원본 이미지 정보 조회
            image_query = (
                sqlalchemy.select(Image.user_id, Image.filename, Image.time_created)
                .where(Image.id == original_image_id)
            )
            image_record = await database.fetch_one(image_query)
            
            if not image_record:
                logger.warning(f"원본 이미지 ID {original_image_id}를 DB에서 찾을 수 없습니다.")
                return
            
            # 이미지 소유자 정보 조회
            user_query = (
                sqlalchemy.select(User.name, User.email)
                .where(User.id == image_record["user_id"])
            )
            user_record = await database.fetch_one(user_query)
            
            if not user_record:
                logger.warning(f"사용자 ID {image_record['user_id']}를 DB에서 찾을 수 없습니다.")
                return
            
            # 위변조 보고서 URL 생성 (실제 구현시 S3 또는 웹사이트 URL로 수정)
            report_url = f"{settings.s3_url}/reports/{original_image_id}"
            
            # 검출 정보 구성
            detection_info = {
                "detection_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "image_name": image_record["filename"],
                "confidence_score": round(verification_result.get("tampering_rate", 0), 2),
                "detected_filename": detected_filename,
                "upload_time": image_record["time_created"].strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # 이메일 발송
            success = await email_service.send_forgery_detection_email(
                user_email=user_record["email"],
                username=user_record["name"],
                detection_info=detection_info,
                report_url=report_url
            )
            
            if success:
                logger.info(f"위변조 알림 이메일이 {user_record['email']}로 발송되었습니다.")
            else:
                logger.error(f"위변조 알림 이메일 발송 실패: {user_record['email']}")
                
        except Exception as e:
            logger.error(f"위변조 알림 처리 중 오류 발생: {str(e)}")
            raise

    async def _get_original_image_copyright(self, image_id: int) -> dict:
        """원본 이미지의 저작권 정보 조회"""
        try:
            logger.info(f"원본 이미지 저작권 정보 조회 시작: image_id={image_id}")
            
            # 이미지와 사용자 정보를 JOIN해서 한번에 조회
            query = (
                sqlalchemy.select(
                    Image.copyright,
                    Image.filename,
                    Image.time_created,
                    Image.protection_algorithm,
                    User.name.label("owner_name"),
                    User.email.label("owner_email")
                )
                .select_from(Image.__table__.join(User.__table__, Image.user_id == User.id))
                .where(Image.id == image_id)
            )
            
            result = await database.fetch_one(query)
            
            if not result:
                logger.warning(f"이미지 ID {image_id}를 찾을 수 없습니다.")
                return {}
            
            copyright_info = {
                "copyright": result["copyright"],
                "filename": result["filename"],
                "upload_time": result["time_created"].isoformat(),
                "protection_algorithm": result["protection_algorithm"],
                "owner_name": result["owner_name"],
                "owner_email": result["owner_email"]
            }
            
            logger.info(f"원본 이미지 저작권 정보 조회 완료: {copyright_info}")
            return copyright_info
            
        except Exception as e:
            logger.error(f"원본 이미지 저작권 정보 조회 실패: {str(e)}")
            import traceback
            logger.error(f"스택 트레이스: {traceback.format_exc()}")
            return {}


image_service = ImageService()
