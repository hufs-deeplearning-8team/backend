import logging
from fastapi import APIRouter, UploadFile, File, Security, Form, Depends, Header
from fastapi.security import APIKeyHeader

from app.schemas import BaseResponse, UserCreate, UserLogin, UserReportRequest, CustomReportRequest, UserReportStats
from app.services.user_service import user_service
from app.services.image_service import image_service
from app.services.validation_service import validation_service
from app.services.email_service import email_service
from app.services.auth_service import auth_service
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
    protection_algorithm: str = Form(..., description="보호 알고리즘 (EditGuard)"),
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
    model: str = Form(..., description="보호 알고리즘 (EditGuard)"),
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

@router.post("/my-weekly-report",
    summary="내 주간 리포트 이메일 발송",
    description="지난 1주일간의 개인 위변조 통계 리포트를 내 이메일로 발송합니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "주간 리포트 발송 완료"},
        401: {"description": "유효하지 않은 토큰"},
        500: {"description": "서버 오류"}
    }
)
async def send_my_weekly_report(
    access_token: str = Security(APIKeyHeader(name='access-token'))
):
    """개인 주간 리포트 이메일 발송"""
    return await validation_service.send_individual_weekly_report(access_token)

@router.post("/admin/send-weekly-reports-now",
    summary="주간 리포트 즉시 발송 (테스트용)",
    description="테스트를 위해 주간 위변조 통계 리포트를 즉시 발송합니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "주간 리포트 발송 완료"},
        500: {"description": "서버 오류"}
    }
)
async def send_weekly_reports_now():
    """테스트용 주간 리포트 즉시 발송 API"""
    try:
        result = await validation_service.send_weekly_reports_to_all_users()
        
        return BaseResponse(
            success=True,
            description="주간 리포트 발송이 완료되었습니다.",
            data=[result]
        )
    except Exception as e:
        logger.error(f"Weekly report sending failed: {str(e)}")
        return BaseResponse(
            success=False,
            description=f"주간 리포트 발송 중 오류가 발생했습니다: {str(e)}",
            data=[]
        )

@router.post("/my-custom-report",
    summary="맞춤 기간 리포트 이메일 발송",
    description="지정한 기간의 개인 위변조 통계 리포트를 내 이메일로 발송합니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "맞춤 기간 리포트 발송 완료"},
        400: {"description": "잘못된 날짜 형식 또는 범위"},
        401: {"description": "유효하지 않은 토큰"},
        500: {"description": "서버 오류"}
    }
)
async def send_my_custom_report(
    report_request: CustomReportRequest,
    access_token: str = Security(APIKeyHeader(name='access-token'))
):
    """개인 맞춤 기간 리포트 이메일 발송"""
    return await validation_service.send_custom_period_report(
        access_token,
        report_request.start_date,
        report_request.end_date
    )


@router.get("/my-hourly-validation-stats",
    summary="대시보드 통계 조회",
    description="지정된 기간의 검증 통계를 조회합니다. 그래프 및 대시보드용 데이터를 제공합니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "통계 조회 성공"},
        400: {"description": "잘못된 기간 파라미터"},
        500: {"description": "통계 조회 실패"}
    }
)
async def get_dashboard_statistics(
    period: str = "7days"
):
    """
    대시보드 통계 조회
    
    Args:
        period: 조회 기간 ("1day", "7days", "30days", "all")
    
    Returns:
        BaseResponse: 통계 데이터를 포함한 응답
    """
    
    # 유효한 기간 검증
    valid_periods = ["1day", "7days", "30days", "all"]
    if period not in valid_periods:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"유효하지 않은 기간입니다. 사용 가능한 값: {', '.join(valid_periods)}"
        )
    
    dashboard_stats = await validation_service.get_dashboard_statistics(period)
    
    return BaseResponse(
        success=True,
        description="대시보드 통계 조회가 완료되었습니다.",
        data=[dashboard_stats.model_dump()]
    )

@router.get("/validation-raw-data",
    summary="원시 검증 데이터 조회",
    description="프론트엔드에서 직접 분석할 수 있도록 단순한 형태의 원시 검증 데이터를 제공합니다. 내가 검증한 것 + 남이 내 이미지로 검증한 것 + 내가 내 것 검증한 것을 모두 포함합니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "원시 데이터 조회 성공"},
        400: {"description": "잘못된 기간 파라미터"},
        401: {"description": "유효하지 않은 토큰"},
        500: {"description": "데이터 조회 실패"}
    }
)
async def get_validation_raw_data(
    period: str = "7days",
    access_token: str = Security(APIKeyHeader(name='access-token'))
):
    """
    원시 검증 데이터 조회
    
    Args:
        period: 조회 기간 ("1day", "7days", "30days", "all")
        access_token: 사용자 인증 토큰
    
    Returns:
        BaseResponse: 단순한 is_tampered + validation_time 배열을 포함한 응답
        
    Response Example:
        {
            "success": true,
            "description": "검증 데이터 조회 완료",
            "data": {
                "period": "7days",
                "validations": [
                    {
                        "is_tampered": false,
                        "validation_time": "2024-01-15T14:30:00Z"
                    },
                    {
                        "is_tampered": true,
                        "validation_time": "2024-01-15T16:45:00Z"
                    }
                ]
            }
        }
    """
    
    # 유효한 기간 검증
    valid_periods = ["1day", "7days", "30days", "all"]
    if period not in valid_periods:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"유효하지 않은 기간입니다. 사용 가능한 값: {', '.join(valid_periods)}"
        )
    
    return await validation_service.get_validation_raw_data(access_token, period)


@router.get("/user-report-stats",
    summary="내 유저 제보 데이터 통계 조회",
    description="내가 제보한 위변조 데이터에서 도메인별 최빈값 상위 5개와 최신 제보 링크 5개를 반환합니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "유저 제보 통계 조회 성공"},
        400: {"description": "잘못된 기간 파라미터"},
        401: {"description": "유효하지 않은 토큰"},
        500: {"description": "서버 오류"}
    }
)
async def get_user_report_statistics(
    access_token: str = Security(APIKeyHeader(name='access-token'))
):
    """
    내 유저 제보 데이터 통계 조회
    
    Args:
        access_token: 사용자 인증 토큰
    
    Returns:
        BaseResponse: 내가 제보한 데이터에서 최빈값 도메인 상위 5개와 최근 제보 링크 5개를 포함한 응답
        
    Response Example:
        {
            "success": true,
            "description": "내 유저 제보 통계를 조회했습니다.",
            "data": [{
                "most_frequent_domains": [
                    {"domain": "example.com", "count": 15},
                    {"domain": "test.com", "count": 12}
                ],
                "recent_report_links": [
                    {"link": "https://example.com/page1", "reported_time": "2025-01-20T15:30:00Z"},
                    {"link": "https://test.com/image2", "reported_time": "2025-01-20T14:20:00Z"}
                ]
            }]
        }
    """
    return await validation_service.get_user_report_statistics(access_token)


# OPEN API 엔드포인트들 (API 키 기반 인증)
@router.post("/open/generate",
    tags=["🔒 워터마크 생성"],
    summary="OPEN API 이미지 생성",
    description="API 키를 사용하여 이미지를 업로드하고 워터마크를 적용합니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "이미지 생성 성공"},
        400: {"description": "잘못된 파일 형식 또는 크기 초과"},
        401: {"description": "유효하지 않은 API 키"},
        500: {"description": "서버 오류"}
    }
)
async def open_generate_image(
    copyright: str = Form(..., description="저작권 정보", max_length=255),
    protection_algorithm: str = Form(..., description="보호 알고리즘 (EditGuard)"),
    file: UploadFile = File(..., description="업로드할 PNG 파일 (최대 10MB)"),
    x_api_key: str = Header(..., alias="X-API-Key", description="API 키")
):
    """API 키를 사용한 이미지 생성"""
    # API 키로 사용자 ID 조회
    user_id = await auth_service.get_user_id_from_api_key(x_api_key)
    
    # 기존 image_service의 upload_image 로직을 재사용하되, API 키 기반으로 인증
    # access_token 대신 user_id를 직접 전달하는 새 메서드 필요
    return await image_service.upload_image_with_user_id(file, copyright, protection_algorithm, user_id)


@router.post("/open/verify", 
    tags=["🔍 이미지 검증"],
    summary="OPEN API 이미지 검증",
    description="API 키를 사용하여 이미지의 위변조 여부를 검증합니다.",
    response_model=BaseResponse,
    responses={
        200: {"description": "이미지 검증 성공"},
        400: {"description": "잘못된 파일 형식"},
        401: {"description": "유효하지 않은 API 키"},
        500: {"description": "서버 오류"}
    }
)
async def open_verify_image(
    file: UploadFile = File(..., description="검증할 PNG 파일"),
    model: str = Form(..., description="보호 알고리즘 (EditGuard)"),
    x_api_key: str = Header(..., alias="X-API-Key", description="API 키")
):
    """API 키를 사용한 이미지 검증"""
    # API 키로 사용자 ID 조회
    user_id = await auth_service.get_user_id_from_api_key(x_api_key)
    
    # 기존 image_service의 verify_image 로직을 재사용하되, API 키 기반으로 인증
    return await image_service.verify_image_with_user_id(file, model, user_id)
