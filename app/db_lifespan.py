from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db import database
from app.services.email_service import email_service
import logging

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 서버 시작 중...")
    
    # 데이터베이스 연결
    await database.connect()
    logger.info("✅ 데이터베이스 연결 완료")
    
    # 이메일 서비스 상태 확인
    email_status = await email_service.check_email_service_status()
    if email_status["smtp_connection"]:
        logger.info("📧 이메일 서비스 준비 완료")
    else:
        logger.warning(f"⚠️ 이메일 서비스 문제: {email_status.get('error', '알 수 없는 오류')}")
    
    logger.info("🎉 서버 시작 완료!")
    
    yield
    
    logger.info("🔄 서버 종료 중...")
    await database.disconnect()
    logger.info("✅ 서버 종료 완료")