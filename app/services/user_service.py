from typing import Optional, Dict, Any
import logging

from fastapi import HTTPException, status
import sqlalchemy

from app.db import database
from app.models import User
from app.schemas import UserCreate, UserLogin, BaseResponse, TokenResponse, UserResponse
from app.services.auth_service import auth_service
from app.services.email_service import email_service

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self):
        self.auth_service = auth_service
    
    async def create_user(self, user_data: UserCreate) -> BaseResponse:
        # 비밀번호 형식 검증
        if not self.auth_service.validate_password(user_data.password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="비밀번호는 8자 이상이며 영문, 숫자, 특수문자를 포함해야 합니다",
                headers={"field": "password"}
            )
        
        # 이름 중복 체크
        name_query = User.__table__.select().where(User.name.collate('utf8mb4_general_ci') == user_data.name)
        existing_name = await database.fetch_one(name_query)
        if existing_name:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, 
                detail="이미 사용 중인 이름입니다",
                headers={"field": "name"}
            )

        # 이메일 중복 체크
        email_query = User.__table__.select().where(User.email.collate('utf8mb4_general_ci') == user_data.email)
        existing_email = await database.fetch_one(email_query)
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, 
                detail="이미 사용 중인 이메일입니다",
                headers={"field": "email"}
            )

        # 비밀번호 해시 및 사용자 생성
        hashed_password = self.auth_service.get_password_hash(user_data.password)
        insert_query = User.__table__.insert().values(
            name=user_data.name, 
            email=user_data.email, 
            password=hashed_password
        )
        await database.execute(insert_query)
        
        # 회원가입 완료 이메일 발송 (비동기, 실패해도 회원가입은 성공)
        try:
            await email_service.send_welcome_email(user_data.email, user_data.name)
            logger.info(f"Welcome email sent to {user_data.email}")
        except Exception as e:
            logger.error(f"Failed to send welcome email to {user_data.email}: {str(e)}")
        
        return BaseResponse(success=True, description="회원가입 성공", data=["OK"])
    
    async def authenticate_user(self, login_data: UserLogin) -> TokenResponse:
        # 사용자 조회
        query = User.__table__.select().where(User.email.collate('utf8mb4_general_ci') == login_data.email)
        db_user = await database.fetch_one(query)
        
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="존재하지 않는 이메일입니다",
                headers={"field": "email"}
            )
        
        # 비밀번호 검증
        if not self.auth_service.verify_password(login_data.password, db_user["password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="비밀번호가 올바르지 않습니다",
                headers={"field": "password"}
            )
        
        # JWT 토큰 생성
        return self.auth_service.create_tokens(db_user["id"])
    
    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        query = User.__table__.select().where(User.id == user_id)
        user = await database.fetch_one(query)
        return dict(user) if user else None
    
    async def verify_token(self, token: str) -> BaseResponse:
        """토큰 유효성만 검증"""
        user_id = self.auth_service.get_user_id_from_token(token)
        return BaseResponse(
            success=True, 
            description="토큰이 유효합니다", 
            data=[{"user_id": user_id, "valid": True}]
        )
    
    async def get_current_user(self, token: str) -> BaseResponse:
        user_id = self.auth_service.get_user_id_from_token(token)
        
        # DB에서 사용자 조회
        user = await self.get_user_by_id(int(user_id))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="User not found"
            )

        return BaseResponse(success=True, description="조회 성공", data=[user])


user_service = UserService()