import logging
from fastapi import APIRouter, UploadFile, File, Security, Form, Depends
from fastapi.security import APIKeyHeader

from app.schemas import BaseResponse, UserCreate, UserLogin, UserReportRequest
from app.services.user_service import user_service
from app.services.image_service import image_service
from app.services.validation_service import validation_service
from app.services.email_service import email_service
from app.models import ProtectionAlgorithm


router = APIRouter()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@router.post("/signup", 
    summary="회원가입",
    description="새 사용자 계정을 생성합니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "회원가입 성공"},
        400: {"description": "이미 사용된 이름 또는 이메일"}
    }
)
async def signup(user: UserCreate):
    return await user_service.create_user(user)




@router.get("/verify-token",
    summary="토큰 검증",
    description="액세스 토큰의 유효성을 검증합니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "토큰이 유효함"},
        401: {"description": "유효하지 않은 토큰"}
    }
)
async def verify_token(token: str = Depends(APIKeyHeader(name="access-token", auto_error=False))):
    return await user_service.verify_token(token)

@router.get("/users/me",
    summary="현재 사용자 정보 조회",
    description="액세스 토큰을 통해 현재 로그인한 사용자의 정보를 조회합니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "사용자 정보 조회 성공"},
        401: {"description": "유효하지 않은 토큰"},
        404: {"description": "사용자를 찾을 수 없음"}
    }
)
async def get_current_user(token: str = Depends(APIKeyHeader(name="access-token", auto_error=False))):
    return await user_service.get_current_user(token)

@router.post("/login",
    summary="로그인",
    description="이메일과 비밀번호로 로그인하여 JWT 토큰을 발급받습니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "로그인 성공 - JWT 토큰 반환"},
        401: {"description": "이메일 또는 비밀번호가 올바르지 않음"}
    }
)
async def login(user: UserLogin):
    tokens = await user_service.authenticate_user(user)
    return BaseResponse(success=True, description="로그인 성공", data=[tokens.dict()])



@router.post("/upload",
    summary="이미지 업로드",
    description="PNG 이미지 파일을 업로드하고 S3에 저장합니다. 저작권 정보도 함께 저장됩니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "파일 업로드 성공"},
        400: {"description": "잘못된 파일 형식 또는 크기 초과"},
        401: {"description": "유효하지 않은 토큰"},
        500: {"description": "S3 업로드 실패"}
    }
)

async def upload(
    copyright: str = Form(..., description="저작권 정보", max_length=255),
    protection_algorithm: str = Form(..., description="보호 알고리즘 (EditGuard, OmniGuard, RobustWide)"),
    file: UploadFile = File(..., description="업로드할 PNG 파일 (최대 10MB)"),
    access_token: str = Security(APIKeyHeader(name='access-token'))
):
    return await image_service.upload_image(file, copyright, protection_algorithm, access_token)

@router.post("/validate",
    summary="이미지 위변조 검증",
    description="업로드된 이미지의 위변조 여부를 AI 서버를 통해 검증합니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "이미지 검증 성공"},
        400: {"description": "잘못된 파일 형식"},
        401: {"description": "유효하지 않은 토큰"}
    }
)
async def validate(
    file: UploadFile = File(..., description="검증할 PNG 파일"),
    model: str = Form(..., description="보호 알고리즘 (EditGuard, OmniGuard, RobustWide)"),
    access_token: str = Security(APIKeyHeader(name='access-token'))
):
    return await validation_service.validate_image(file, model, access_token)

@router.get("/algorithms",
    summary="보호 알고리즘 목록 및 설명",
    description="사용 가능한 보호 알고리즘 목록과 각각의 설명을 제공합니다.",
    response_model=BaseResponse
)
async def get_algorithms():
    """보호 알고리즘 목록과 설명 반환"""
    algorithms = {
        "EditGuard": {
            "name": "EditGuard",
            "title": "어디가 변조되었는지 증명해야 할 때",
            "description": "딥페이크, 허위 정보 등 조작된 영역을 95% 이상 정밀도로 탐지\n언론 보도, 법적 분쟁 등 조작의 범위와 내용 증명이 핵심일 때 최적의 솔루션"
        },
        "RobustWide": {
            "name": "RobustWide", 
            "title": "어떤 공격에도 원본임을 지켜내야 할 때",
            "description": "강력한 AI 편집 공격에도 워터마크가 훼손되지 않는 최고의 생존력\n웹툰, 캐릭터 등 고부가가치 IP 자산이나 브랜드 로고를 보호할 때 가장 효과적"
        }
    }
    
    return BaseResponse(
        success=True,
        message="알고리즘 목록 조회 성공",
        data=[algorithms]
    )



@router.get("/validation-history",
    summary="검증 기록 조회",
    description="현재 사용자의 이미지 검증 기록을 조회합니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "검증 기록 조회 성공"},
        401: {"description": "유효하지 않은 토큰"}
    }
)
async def get_validation_history(
    access_token: str = Security(APIKeyHeader(name='access-token')),
    limit: int = 10,
    offset: int = 0
):
    return await validation_service.get_validation_history(access_token, limit, offset)

@router.get("/validation-record/uuid/{validation_uuid}",
    summary="UUID로 검증 레코드 조회",
    description="UUID를 사용하여 특정 검증 레코드를 조회합니다. (인증 불필요)",
    response_model=BaseResponse,
    responses={
        200: {"description": "검증 레코드 조회 성공"},
        404: {"description": "검증 레코드를 찾을 수 없음"}
    }
)
async def get_validation_record_by_uuid(validation_uuid: str):
    return await validation_service.get_validation_record_by_uuid_public(validation_uuid)

@router.get("/validation-record/id/{record_id}",
    summary="ID로 검증 레코드 조회",
    description="레코드 ID를 사용하여 특정 검증 레코드를 조회합니다. (인증 불필요)",
    response_model=BaseResponse,
    responses={
        200: {"description": "검증 레코드 조회 성공"},
        404: {"description": "검증 레코드를 찾을 수 없음"}
    }
)
async def get_validation_record_by_id(record_id: int):
    return await validation_service.get_validation_record_by_id_public(record_id)

@router.get("/validation-records/user/{target_user_id}",
    summary="User ID로 검증 레코드 목록 조회",
    description="특정 사용자의 모든 검증 레코드를 조회합니다. (인증 불필요)",
    response_model=BaseResponse,
    responses={
        200: {"description": "검증 레코드 목록 조회 성공"}
    }
)
async def get_validation_records_by_user_id(
    target_user_id: int,
    limit: int = 20,
    offset: int = 0
):
    return await validation_service.get_validation_records_by_user_id_public(target_user_id, limit, offset)

@router.get("/images",
    summary="내가 업로드한 이미지 목록 조회",
    description="현재 사용자가 업로드한 이미지 목록을 조회합니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "업로드한 이미지 목록 조회 성공"},
        401: {"description": "유효하지 않은 토큰"}
    }
)
async def get_my_images(
    access_token: str = Security(APIKeyHeader(name='access-token')),
    limit: int = 20,
    offset: int = 0
):
    return await image_service.get_user_images(access_token, limit, offset)

@router.get("/my-validation-summary",
    summary="내 위변조 검증 요약 정보 조회",
    description="현재 사용자의 검증 내역과 업로드 이미지 수, 검증 횟수를 포함한 요약 정보를 조회합니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "검증 요약 정보 조회 성공"},
        401: {"description": "유효하지 않은 토큰"}
    }
)
async def get_my_validation_summary(
    access_token: str = Security(APIKeyHeader(name='access-token')),
    limit: int = 10,
    offset: int = 0
):
    return await validation_service.get_validation_summary(access_token, limit, offset)

@router.get("/my-validation-summary2",
    summary="내 위변조 검증 통합 요약 정보 조회",
    description="내가 검증한 데이터와 내 이미지가 검증된 데이터를 모두 포함하여 조회합니다. 각 레코드는 관계 유형으로 구분됩니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "통합 검증 요약 정보 조회 성공"},
        401: {"description": "유효하지 않은 토큰"}
    }
)
async def get_my_validation_summary2(
    access_token: str = Security(APIKeyHeader(name='access-token')),
    limit: int = 20,
    offset: int = 0
):
    return await validation_service.get_validation_summary2(access_token, limit, offset)

@router.get("/test-s3",
    summary="S3 연결 테스트",
    description="S3 연결 상태를 테스트합니다.",
    response_model=BaseResponse
)
async def test_s3_connection():
    from app.services.storage_service import storage_service
    
    # 연결 테스트
    connection_ok = await storage_service.test_s3_connection()
    
    # 업로드 테스트
    upload_ok = False
    if connection_ok:
        upload_ok = await storage_service.test_upload()
    
    return BaseResponse(
        success=connection_ok and upload_ok,
        description="S3 테스트 완료",
        data=[{
            "connection": connection_ok,
            "upload": upload_ok,
            "endpoint": image_service.storage_service.s3_client._endpoint.host,
            "bucket": image_service.storage_service.bucket_name
        }]
    )

@router.get("/protection-algorithms",
    summary="보호 알고리즘 목록 조회",
    description="사용 가능한 이미지 보호 알고리즘 목록을 조회합니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "보호 알고리즘 목록 조회 성공"}
    }
)
async def get_protection_algorithms():
    algorithms = [{"value": alg.value, "name": alg.value} for alg in ProtectionAlgorithm]
    return BaseResponse(
        success=True,
        description="보호 알고리즘 목록을 조회했습니다.",
        data=algorithms
    )

@router.put("/user-report",
    summary="사용자 제보 정보 업데이트",
    description="위변조 검출된 검증에 대해 사용자가 제보 정보를 추가/업데이트합니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "제보 정보 업데이트 성공"},
        400: {"description": "위변조가 검출되지 않은 검증이거나 잘못된 요청"},
        401: {"description": "유효하지 않은 토큰"},
        403: {"description": "권한 없음 - 본인이 수행한 검증만 제보 가능"},
        404: {"description": "검증 레코드를 찾을 수 없음"}
    }
)
async def update_user_report(
    report_data: UserReportRequest,
    access_token: str = Security(APIKeyHeader(name='access-token'))
):
    return await validation_service.update_user_report(report_data, access_token)

