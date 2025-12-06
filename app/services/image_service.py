import logging
from typing import List, Dict, Any, Optional
import base64
from fastapi import HTTPException, status, UploadFile
import sqlalchemy
import httpx
from datetime import datetime

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
    
    async def _send_to_ai_server(self, image_content: bytes, image_id:int, model:ProtectionAlgorithm) -> bytes:
        """EditGuard 워터마크 API에 이미지를 전송하고 워터마크된 이미지를 받아온다"""
        try:
            api_server_url = self._get_watermark_api_base_url()
            watermark_payload = self._encode_image_id_to_watermark(image_id)
            data = {
                "watermark": watermark_payload
            }
            logger.info(f"{model.value} watermark payload for image_id {image_id}: {watermark_payload}")
            files = {
                "image": (f"image_{image_id}.png", image_content, "image/png")
            }
            endpoint = f"{api_server_url}/watermark/embed"
            logger.info(f"{model.value} 알고리즘: EditGuard API({endpoint}) 사용")
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(endpoint, data=data, files=files)
            response_text = response.text
            
            if response.status_code != 200:
                truncated = response_text[:500]
                logger.error(f"EditGuard embed API returned {response.status_code}: {truncated}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"AI 서버 오류: {response.text}"
                )
            
            try:
                response_data = response.json()
            except ValueError as parse_error:
                logger.error(f"EditGuard embed API JSON 파싱 실패: {parse_error}. 원본 응답: {response_text[:500]}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="EditGuard API 응답 파싱 실패"
                )
            
            sanitized_response_log = dict(response_data)
            if "watermarked_image" in sanitized_response_log:
                sanitized_response_log["watermarked_image"] = "<omitted>"
            logger.info(f"EditGuard embed API response (image omitted): {sanitized_response_log}")
            
            response_watermark = str(response_data.get("watermark"))
            if response_watermark == watermark_payload:
                logger.info(f"EditGuard embed watermark verification passed for image_id {image_id}")
            else:
                logger.warning(
                    f"EditGuard embed watermark mismatch for image_id {image_id}. sent={watermark_payload}, received={response_watermark}"
                )
            
            if not response_data.get("success"):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="EditGuard API에서 워터마크 처리 실패"
                )
            watermarked_b64 = response_data.get("watermarked_image")
            if not watermarked_b64:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="EditGuard API 응답에 워터마크 이미지가 없습니다."
                )
            
            return base64.b64decode(watermarked_b64)
                
        except httpx.TimeoutException:
            logger.error("AI 서버 요청 타임아웃")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="AI 서버 응답 시간 초과"
            )
        except Exception as e:
            logger.error(f"AI 서버 통신 오류: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"AI 서버 통신 중 오류가 발생했습니다: {str(e)}"
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
    
    async def _send_to_ai_server_for_verification(self, image_content: bytes, model: ProtectionAlgorithm) -> dict:
        try:
            return await self._verify_with_editguard_server(image_content, model)
                
        except httpx.TimeoutException:
            logger.error("AI 서버 검증 요청 타임아웃")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="AI 서버 응답 시간 초과"
            )
        except Exception as e:
            logger.error(f"AI 서버 검증 통신 오류: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"AI 서버 통신 중 오류가 발생했습니다: {str(e)}"
            )

    async def _verify_with_editguard_server(self, image_content: bytes, model: ProtectionAlgorithm, threshold: float = 0.2) -> dict:
        api_server_url = self._get_watermark_api_base_url()
        data = {
            "threshold": str(threshold)
        }
        files = {
            "image": (f"verify_{model.value}.png", image_content, "image/png")
        }
        endpoint = f"{api_server_url}/watermark/extract"
        logger.info(f"{model.value} 검증: EditGuard API({endpoint}) 사용")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(endpoint, data=data, files=files)
        logger.info(f"EditGuard API raw response: {response.text}")
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"EditGuard API 오류: {response.text}"
            )
        response_data = response.json()
        logger.info(f"EditGuard API 응답: {response_data}")
        
        if not response_data.get("success"):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="EditGuard API에서 검증 처리 실패"
            )
        
        watermark_bits = response_data.get("watermark", "")
        direct_original_id = response_data.get("original_image_id")
        original_image_id = None

        if direct_original_id is not None:
            try:
                original_image_id = int(direct_original_id)
            except (TypeError, ValueError):
                logger.warning(f"EditGuard API original_image_id 변환 실패: {direct_original_id}")
                original_image_id = None

        if original_image_id is None:
            original_image_id = self._decode_watermark_bits(watermark_bits)

        mask_data = response_data.get("tamper_mask", "") or ""
        tamper_ratio = float(response_data.get("tamper_ratio", 0.0) or 0.0)
        tampering_rate = tamper_ratio * 100
        
        return {
            "ai_tampering_rate": tampering_rate,
            "tampering_rate": tampering_rate,
            "tampered_regions_mask": mask_data,
            "original_image_id": original_image_id,
            "tamper_detected": response_data.get("tamper_detected", False)
        }

    def _get_watermark_api_base_url(self) -> str:
        api_server_url = settings.AI_IP
        if not api_server_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="워터마크 API 서버 주소가 설정되지 않았습니다."
            )
        return api_server_url.rstrip('/')

    def _encode_image_id_to_watermark(self, image_id: int) -> str:
        """이미지 ID를 64비트 0/1 문자열로 변환"""
        if image_id < 0:
            raise ValueError("image_id는 0 이상이어야 합니다")
        if image_id >= 2 ** 64:
            raise ValueError("image_id가 64비트를 초과합니다")
        return f"{image_id:064b}"

    def _decode_watermark_bits(self, bit_string: str) -> Optional[int]:
        """64비트 0/1 문자열을 정수 이미지 ID로 복원"""
        if not bit_string:
            return None
        sanitized = str(bit_string).strip()
        if len(sanitized) != 64:
            logger.warning(f"워터마크 비트 길이가 예상과 다릅니다: {len(sanitized)}")
            return None
        if any(ch not in "01" for ch in sanitized):
            logger.error("워터마크 문자열에 0/1 이외의 문자가 포함되어 있습니다")
            return None
        try:
            return int(sanitized, 2)
        except Exception as error:
            logger.error(f"워터마크 디코딩 실패: {error}")
            return None

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
