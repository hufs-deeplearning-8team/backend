import logging
from typing import List, Dict, Any
import base64
import numpy as np
import galois
from fastapi import HTTPException, status, UploadFile
import sqlalchemy
import httpx

from app.config import settings
from app.db import database
from app.models import Image, ProtectionAlgorithm
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
        
        # DB에 이미지 정보 저장
        query = (
            sqlalchemy.insert(Image)
            .values(
                user_id=int(user_id), 
                copyright=copyright, 
                filename=original_filename,
                protection_algorithm=protection_enum
            )
            .returning(Image)
        )
        
        result = await database.fetch_one(query)
        inserted_data = dict(result)
        image_id = inserted_data["id"]

        logger.info(f"Image uploaded to DB: {inserted_data}")
        
        try:
            # 임시: AI 서버 코드 오류로 인해 원본 이미지 사용
            watermarked_image_content = await self._send_to_ai_server(file_content, image_id, protection_enum)
            # watermarked_image_content = file_content
            
            # S3에 원본(GT)과 워터마크(SRH) 이미지 업로드
            gt_path = f"image/{image_id}/gt.png"
            srh_path = f"image/{image_id}/sr_h.png"
            
            await self.storage_service.upload_file(file_content, gt_path)
            await self.storage_service.upload_file(watermarked_image_content, srh_path)
            logger.info(f"Files uploaded to S3: GT={gt_path}, SRH={srh_path}")
            
        except Exception as e:
            # AI 서버 또는 S3 업로드 실패 시 DB에서 해당 레코드 삭제
            logger.error(f"AI 서버 또는 S3 업로드 실패: {str(e)}")
            delete_query = sqlalchemy.delete(Image).where(Image.id == image_id)
            await database.execute(delete_query)
            logger.info(f"Rolled back DB record for image_id: {image_id}")
            raise
        
        return BaseResponse(
            success=True, 
            description="생성 성공", 
            data=[inserted_data]
        )
    
    async def _send_to_ai_server(self, image_content: bytes, image_id:int, model:ProtectionAlgorithm) -> bytes:
        """AI 서버에 이미지를 전송하고 워터마크된 이미지를 받아온다"""
        try:
            # 이미지를 base64로 인코딩
            image_b64 = base64.b64encode(image_content).decode('utf-8')

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
                
                # base64 디코딩하여 바이너리 데이터 반환
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
                    "tampering_rate": calculated_tampering_rate,  # 계산된 변조률 사용
                    "ai_tampering_rate": data.get("acc", 0),  # AI 서버 응답 변조률 (참고용)
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


image_service = ImageService()