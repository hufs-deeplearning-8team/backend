import os
from typing import Optional

# 환경 구분: AWS 배포 환경인지 확인
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
IS_PRODUCTION = ENVIRONMENT == "production"

# 로컬 개발환경에서만 .env 파일 로드
if not IS_PRODUCTION:
    try:
        from dotenv import load_dotenv
        load_dotenv()  # 로컬 테스트환경에서 .env 파일 로드
        print("🔧 로컬 개발환경: .env 파일을 로드했습니다.")
    except ImportError:
        print("⚠️ python-dotenv가 설치되지 않았습니다.")


class Settings:
    # Environment Settings
    ENVIRONMENT: str = ENVIRONMENT
    IS_PRODUCTION: bool = IS_PRODUCTION
    
    # Database Settings
    DB_USER: str = os.getenv("DB_USER")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD")
    DB_HOST: str = os.getenv("DB_HOST")
    DB_PORT: str = os.getenv("DB_PORT")
    DB_NAME: str = os.getenv("DB_NAME")
    
    def __init__(self):
        # 환경 정보 출력
        print(f"🚀 애플리케이션 시작 - 환경: {self.ENVIRONMENT}")
        if self.IS_PRODUCTION:
            print("📦 AWS 프로덕션 환경에서 실행 중")
        else:
            print("🔧 로컬 개발환경에서 실행 중")
            # 로컬에서만 디버깅 정보 출력
            print(f"=== Environment Variables Debug ===")
            print(f"DB_HOST: {self.DB_HOST}")
            print(f"DB_USER: {self.DB_USER}")
            print(f"DB_PORT: {self.DB_PORT}")
            print(f"DB_NAME: {self.DB_NAME}")
            print(f"=====================================")
    
    @property
    def async_database_url(self) -> str:
        return f"mysql+asyncmy://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4&init_command=SET time_zone = '+09:00'"
    
    @property
    def sync_database_url(self) -> str:
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
    
    # JWT Settings
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS"))
    
    # AWS S3 Settings
    AWS_ACCESS_KEY_ID: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID") 
    AWS_SECRET_ACCESS_KEY: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION_NAME: str = os.getenv("AWS_REGION_NAME")

    print(AWS_REGION_NAME)

    # S3 Bucket Settings
    S3_DEPLOYMENT_BUCKET: str = os.getenv("S3_DEPLOYMENT_BUCKET")
    IMAGEDIR: str = os.getenv("IMAGEDIR")
    RECORDDIR: str = os.getenv("RECORDDIR")

    
    # File Upload Settings
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_FILE_TYPES: list = [".png"]
    ALLOWED_CONTENT_TYPES: list = ["image/png"]
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # AI Server Settings
    AI_IP: str = os.getenv("AI_IP")
    AI_IP2: str = os.getenv("AI_IP2")
    
    # Email Settings
    SMTP_HOST: str = os.getenv("SMTP_HOST")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT") or "587")
    SMTP_USER: str = os.getenv("SMTP_USER")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    EMAIL_FROM: str = os.getenv("EMAIL_FROM")
    EMAIL_FROM_NAME: str = os.getenv("EMAIL_FROM_NAME") or "Aegis Security System"
    
    # Frontend Settings
    FRONTEND_BASE_URL: str = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")

    @property
    def s3_url(self) -> str:
        """AWS S3 버킷 URL"""
        if not self.S3_DEPLOYMENT_BUCKET or not self.AWS_REGION_NAME:
            raise ValueError("S3_DEPLOYMENT_BUCKET과 AWS_REGION_NAME이 설정되어야 합니다")
        return f"https://{self.S3_DEPLOYMENT_BUCKET}.s3.{self.AWS_REGION_NAME}.amazonaws.com"
    @property 
    def s3_image_dir(self) -> str:
        return f"{self.s3_url}/{self.IMAGEDIR}"
    
    @property
    def s3_record_dir(self) -> str:
        return f"{self.s3_url}/{self.RECORDDIR}"


settings = Settings()

# Legacy exports for backward compatibility
DB_USER = settings.DB_USER
DB_PASSWORD = settings.DB_PASSWORD  
DB_HOST = settings.DB_HOST
DB_PORT = settings.DB_PORT
DB_NAME = settings.DB_NAME
ASYNC_DATABASE_URL = settings.async_database_url
SYNC_DATABASE_URL = settings.sync_database_url 
AI_IP = settings.AI_IP
AI_IP2 = settings.AI_IP2



import galois
n = 63
t = 4
d = 2 * t + 1
bch = galois.BCH(n, d=d)
