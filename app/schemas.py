from typing import List, Any, Optional
from pydantic import BaseModel, Field, EmailStr


class BaseResponse(BaseModel):
    success: bool = Field(True, description="요청 성공 여부")
    description: Optional[str] = Field(None, description="응답 설명")
    data: List[Any] = Field(description="응답 데이터")


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="에러 메시지")
    error_code: Optional[str] = Field(None, description="에러 코드")
    field: Optional[str] = Field(None, description="에러가 발생한 필드")


class UserCreate(BaseModel):
    name: str = Field(..., description="사용자 이름", min_length=1, max_length=255)
    email: EmailStr = Field(..., description="이메일 주소")
    password: str = Field(..., description="비밀번호", min_length=6)


class UserLogin(BaseModel):
    email: EmailStr = Field(..., description="이메일 주소")
    password: str = Field(..., description="비밀번호")


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    time_created: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AIValidationRequest(BaseModel):
    input_image_base64: str = Field(..., description="입력 이미지 Base64 데이터")
    filename: str = Field(..., description="파일명")


class AIValidationResponse(BaseModel):
    has_watermark: bool = Field(..., description="워터마크 존재 여부")
    detected_watermark_image_id: Optional[int] = Field(None, description="감지된 워터마크 이미지 ID")
    modification_rate: Optional[float] = Field(None, description="변조율 (0.0 ~ 1.0)")
    visualization_image_base64: Optional[str] = Field(None, description="변조 시각화 이미지 (Base64)")


class ValidationResponse(BaseModel):
    validation_id: str
    has_watermark: bool
    detected_watermark_image_id: Optional[int]
    modification_rate: Optional[float]
    input_filename: str
    validation_time: Optional[str]
    input_image_base64: str
    visualization_image_base64: Optional[str]


class ImageUploadResponse(BaseModel):
    image_id: int
    filename: str
    copyright: str
    upload_time: str
    s3_paths: dict


class ValidationHistoryItem(BaseModel):
    validation_id: str
    input_filename: str
    has_watermark: bool
    detected_watermark_image_id: Optional[int]
    modification_rate: Optional[float]
    validation_time: str


class ValidationSummary(BaseModel):
    user_statistics: dict
    validation_history: List[ValidationHistoryItem]


class UserReportRequest(BaseModel):
    validation_uuid: str = Field(..., description="검증 레코드 UUID", min_length=36, max_length=36)
    report_link: Optional[str] = Field(None, description="위변조 이미지 습득 링크", max_length=2000)
    report_text: Optional[str] = Field(None, description="위변조 관련 상세 설명", max_length=10000)

    class Config:
        json_schema_extra = {
            "example": {
                "validation_uuid": "123e4567-e89b-12d3-a456-426614174000",
                "report_link": "https://example.com/image-source",
                "report_text": "이 이미지는 SNS에서 발견되었으며, 원본과 비교했을 때 명백한 변조 흔적이 있습니다."
            }
        }


class UserReportResponse(BaseModel):
    validation_uuid: str
    report_link: Optional[str]
    report_text: Optional[str]
    updated_time: str


class CustomReportRequest(BaseModel):
    start_date: str = Field(..., description="시작 날짜 (YYYY-MM-DD 형식)", pattern=r'^\d{4}-\d{2}-\d{2}$')
    end_date: str = Field(..., description="종료 날짜 (YYYY-MM-DD 형식)", pattern=r'^\d{4}-\d{2}-\d{2}$')

    class Config:
        json_schema_extra = {
            "example": {
                "start_date": "2024-01-01",
                "end_date": "2024-01-07"
            }
        }


# 대시보드 통계 스키마들
class DailyStat(BaseModel):
    date: str = Field(..., description="날짜 (YYYY-MM-DD)")
    validations: int = Field(..., description="해당 날짜 검증수")
    forgeries: int = Field(..., description="해당 날짜 위변조 검출수")
    active_users: int = Field(..., description="해당 날짜 활성 사용자수")


class DashboardSummary(BaseModel):
    total_validations: int = Field(..., description="총 검증수")
    total_forgeries: int = Field(..., description="총 위변조 검출수")
    detection_rate: float = Field(..., description="위변조 검출율 (%)")
    active_users: int = Field(..., description="활성 사용자수")
    total_images: int = Field(..., description="총 업로드된 이미지수")


class PeriodComparison(BaseModel):
    current_validations: int = Field(..., description="현재 기간 검증수")
    current_forgeries: int = Field(..., description="현재 기간 위변조수")
    previous_validations: int = Field(..., description="이전 기간 검증수")
    previous_forgeries: int = Field(..., description="이전 기간 위변조수")
    validation_growth_rate: float = Field(..., description="검증수 증감률 (%)")
    forgery_growth_rate: float = Field(..., description="위변조 증감률 (%)")


class DashboardStats(BaseModel):
    period: str = Field(..., description="조회 기간 (1day, 7days, 30days, all)")
    summary: DashboardSummary = Field(..., description="요약 통계")
    daily_data: List[DailyStat] = Field(..., description="일별 데이터")
    comparison: PeriodComparison = Field(..., description="이전 기간 대비 비교")
    
    class Config:
        json_schema_extra = {
            "example": {
                "period": "7days",
                "summary": {
                    "total_validations": 1250,
                    "total_forgeries": 85,
                    "detection_rate": 6.8,
                    "active_users": 45,
                    "total_images": 320
                },
                "daily_data": [
                    {"date": "2025-01-20", "validations": 150, "forgeries": 12, "active_users": 8},
                    {"date": "2025-01-19", "validations": 89, "forgeries": 8, "active_users": 6}
                ],
                "comparison": {
                    "current_validations": 1250,
                    "current_forgeries": 85,
                    "previous_validations": 1100,
                    "previous_forgeries": 78,
                    "validation_growth_rate": 13.6,
                    "forgery_growth_rate": 9.0
                }
            }
        }


# 개인 시간별 통계 스키마들
class HourlyValidationStat(BaseModel):
    hour: int = Field(..., description="시간 (0-23)")
    total_validations: int = Field(..., description="해당 시간대 전체 검증수")
    forgeries_detected: int = Field(..., description="해당 시간대 위변조 감지수")

class UserValidationStats(BaseModel):
    my_validations: int = Field(..., description="내가 수행한 검증수")
    others_validated_my_images: int = Field(..., description="타인이 내 이미지를 검증한 수")
    my_self_validations: int = Field(..., description="내가 내 이미지를 검증한 수")
    my_forgeries: int = Field(..., description="내 검증 중 위변조 감지수")
    others_found_forgeries_in_my_images: int = Field(..., description="타인이 내 이미지에서 위변조 감지한 수")
    my_self_found_forgeries: int = Field(..., description="내가 내 이미지에서 위변조 감지한 수")

class HourlyUserValidationStats(BaseModel):
    period: str = Field(..., description="조회 기간 (7days, 30days)")
    user_stats: UserValidationStats = Field(..., description="사용자 전체 통계")
    hourly_data: List[HourlyValidationStat] = Field(..., description="시간대별 통계")
    
    class Config:
        json_schema_extra = {
            "example": {
                "period": "7days",
                "user_stats": {
                    "my_validations": 45,
                    "others_validated_my_images": 23,
                    "my_self_validations": 12,
                    "my_forgeries": 8,
                    "others_found_forgeries_in_my_images": 3,
                    "my_self_found_forgeries": 2
                },
                "hourly_data": [
                    {"hour": 0, "total_validations": 2, "forgeries_detected": 0},
                    {"hour": 9, "total_validations": 15, "forgeries_detected": 3},
                    {"hour": 14, "total_validations": 8, "forgeries_detected": 1}
                ]
            }
        }


# 유저 제보 통계 스키마들
class DomainFrequency(BaseModel):
    domain: str = Field(..., description="도메인명")
    count: int = Field(..., description="해당 도메인 빈도수")


class RecentReportLink(BaseModel):
    link: str = Field(..., description="제보 링크")
    reported_time: str = Field(..., description="제보 시간")


class UserReportStats(BaseModel):
    most_frequent_domains: List[DomainFrequency] = Field(..., description="최빈값 상위 5개 도메인")
    recent_report_links: List[RecentReportLink] = Field(..., description="최근 제보 링크 5개")
    
    class Config:
        json_schema_extra = {
            "example": {
                "most_frequent_domains": [
                    {"domain": "example.com", "count": 15},
                    {"domain": "test.com", "count": 12},
                    {"domain": "sample.org", "count": 8},
                    {"domain": "demo.net", "count": 5},
                    {"domain": "fake.co", "count": 3}
                ],
                "recent_report_links": [
                    {"link": "https://example.com/page1", "reported_time": "2025-01-20T15:30:00Z"},
                    {"link": "https://test.com/image2", "reported_time": "2025-01-20T14:20:00Z"},
                    {"link": "https://sample.org/post3", "reported_time": "2025-01-20T13:10:00Z"},
                    {"link": "https://demo.net/content4", "reported_time": "2025-01-20T12:45:00Z"},
                    {"link": "https://fake.co/item5", "reported_time": "2025-01-20T11:30:00Z"}
                ]
            }
        }