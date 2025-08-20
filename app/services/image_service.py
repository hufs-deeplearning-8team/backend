import logging
from typing import List, Dict, Any
import base64
import numpy as np
import galois
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
            query = (
                sqlalchemy.insert(Image)
                .values(
                    user_id=int(user_id), 
                    copyright=copyright, 
                    filename=original_filename,
                    protection_algorithm=protection_enum,
                    use_openapi=False
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
            query = (
                sqlalchemy.insert(Image)
                .values(
                    user_id=int(user_id), 
                    copyright=copyright, 
                    filename=original_filename,
                    protection_algorithm=protection_enum,
                    use_openapi=True
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
        """AI 서버에 이미지를 전송하고 워터마크된 이미지를 받아온다"""
        try:
            # 이미지를 base64로 인코딩
            image_b64 = base64.b64encode(image_content).decode('utf-8')

            # FAKEFACE 알고리즘은 테스트용으로 더미 처리
            if model == ProtectionAlgorithm.FAKEFACE:
                logger.info(f"FAKEFACE 테스트: 입력 이미지를 그대로 반환 (이미지 크기: {len(image_content)} bytes)")
                # 테스트용으로 원본 이미지를 그대로 반환
                return image_content
            else:
                # RobustWide, EditGuard는 기존 로직 사용
                # id 인코딩
                n = 63
                t = 4
                d = 2 * t + 1
                bch = galois.BCH(n, d=d)
                image_id_bit = f"{image_id:039b}"
                image_id_bit_array = np.array([int(bit) for bit in image_id_bit])
                codeword_array = bch.encode(image_id_bit_array)
                codeword_string = "".join(str(bit) for bit in codeword_array)+'0'

                # AI 서버로 전송할 데이터 구성
                payload = {
                    "image": image_b64,
                    "bit_input": f"{codeword_string}",
                    "model": model.value
                }
            
                # AI 서버에 요청
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"{settings.AI_IP}/upload",
                        json=payload
                    )
                
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"AI 서버 오류: {response.text}"
                    )
                
                response_data = response.json()
                
                if not response_data.get("success"):
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="AI 서버에서 워터마크 처리 실패"
                    )
                
                # base64 디코딩하여 바이너리 데이터 반환 (RobustWide, EditGuard)
                watermarked_b64 = response_data["data"]["lr"]
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
            # 이미지를 base64로 인코딩
            image_b64 = base64.b64encode(image_content).decode('utf-8')
            
            # AI 서버로 전송할 데이터 구성
            payload = {
                "sr_h": image_b64,
                "model": model.value
            }
            
            # AI 서버에 요청
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{settings.AI_IP}/verify",
                    json=payload
                )
                
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"AI 서버 오류: {response.text}"
                    )
                
                response_data = response.json()
                logger.info(f"AI 서버 응답: {response_data}")
                
                if not response_data.get("success"):
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="AI 서버에서 검증 처리 실패"
                    )
                
                # 응답 데이터 구조에 따라 안전하게 접근
                data = response_data.get("data", {})
                mask_data = data.get("mask", "")
                recovered_bit = data.get("recovered_bit", "0")

               
                # 1. BCH 파라미터 정의
                # m=6에 해당 -> n = 2^6 - 1 = 63
                n = 63
                # 복구할 비트 수 (t=4로 설정)
                t = 4
                # 설계 거리 d 계산
                d = 2 * t + 1
                # 2. BCH 코드 생성
                bch = galois.BCH(n, d=d)

                logger.info(f"BCH 코드 생성 완료: n={n}, d={d}")
                # recovered_bit를 이진 문자열을 정수로 변환
                recovered_bit_array = np.array([int(bit) for bit in recovered_bit[0:-1]])
                decoded_bit_array = bch.decode(recovered_bit_array, errors=True)
                decoded_bit = "".join(str(bit) for bit in decoded_bit_array[0])
                logger.info(f"Decoded bit: {decoded_bit}, type: {type(decoded_bit)}")
                original_image_id = int(decoded_bit, 2)

                logger.info(f"Recovered bit: {recovered_bit}, type: {type(recovered_bit)}")
                logger.info(f"Original image ID: {original_image_id}, type: {type(original_image_id)}")
                logger.info(f"Decoded bit array: {decoded_bit_array}, type: {type(decoded_bit_array)}") 


                # mask 데이터에서 변조률 계산
                calculated_tampering_rate = 0.0
                if mask_data:
                    try:
                        # mask base64 디코딩해서 이미지로 변환
                        from PIL import Image as PILImage
                        import io
                        
                        mask_bytes = base64.b64decode(mask_data)
                        
                        logger.info(f"Mask 바이트 크기: {len(mask_bytes)}")
                        logger.info(f"Mask base64 처음 100자: {mask_data[:100]}...")
                        
                        # PIL로 이미지 열기 시도
                        mask_image = PILImage.open(io.BytesIO(mask_bytes))
                        logger.info(f"Mask 이미지 모드: {mask_image.mode}, 크기: {mask_image.size}")
                        
                        # grayscale로 변환 (1과 0의 마스크이므로)
                        if mask_image.mode != 'L':
                            mask_image = mask_image.convert('L')
                        
                        # numpy 배열로 변환
                        mask_array = np.array(mask_image)
                        
                        # 0과 1로 이루어진 mask에서 1의 개수로 변조률 계산
                        # 픽셀값을 0 또는 1로 정규화 (0은 정상, 1은 변조)
                        binary_mask = (mask_array > 0).astype(int)  # 0보다 큰 값은 모두 1로 변환
                        
                        total_pixels = binary_mask.size
                        modified_pixels = np.sum(binary_mask)  # 1의 개수
                        
                        calculated_tampering_rate = (modified_pixels / total_pixels * 100) if total_pixels > 0 else 0.0  # 백분율로 변환
                        
                        logger.info(f"Mask 이미지 크기: {mask_image.size}")
                        logger.info(f"원본 픽셀값 분포 - Min: {np.min(mask_array)}, Max: {np.max(mask_array)}")
                        logger.info(f"이진화 후 - 0의 개수: {np.sum(binary_mask == 0)}, 1의 개수: {modified_pixels}")
                        logger.info(f"변조률: {modified_pixels}/{total_pixels} = {calculated_tampering_rate:.4f}%")
                        
                    except Exception as e:
                        logger.info(f"Mask 변조률 계산 실패: {e}")
                        calculated_tampering_rate = data.get("acc", 0)  # AI 서버 응답 사용
                else:
                    logger.info("Mask 데이터 없음")
                    calculated_tampering_rate = data.get("acc", 0)  # AI 서버 응답 사용
                
                return {
                    "ai_tampering_rate": data.get("acc", 0),  # AI 서버 응답 변조률
                    "tampered_regions_mask": mask_data,  # 변조된 부분 (base64 이미지)
                    "original_image_id": original_image_id  # 원본 이미지 ID (이진→정수)
                }
                
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