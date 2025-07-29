from fastapi import APIRouter
from pydantic import EmailStr
from passlib.context import CryptContext
from app.models import User, Image
from app.db import database
from datetime import  timedelta
from fastapi.security import APIKeyHeader
from fastapi import Depends
from jose import JWTError, jwt
import sqlalchemy


from fastapi import HTTPException, status, UploadFile, File, Security
from datetime import datetime
import io


from typing import List, Any, Optional
from pydantic import BaseModel

class BaseResponse(BaseModel):
    success: bool = True
    description: Optional[str] = None
    data: List[Any]

# ============================= S3 셋팅 =========================================
import os
import boto3
from botocore.client import Config

s3 = boto3.client(
    's3',
    endpoint_url=os.getenv("AWS_S3_ENDPOINT"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    config=Config(signature_version=os.getenv("AWS_SIGNATURE_VERSION")),
    region_name=os.getenv("AWS_REGION_NAME")
)

BUCKET_NAME = os.getenv('BUCKET_NAME')

# ================================================================================

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = os.getenv("JWT_ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS"))

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def validate_file(file):
    if not file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is required")
    if not file.filename.endswith(".png"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PNG files are allowed")
    if file.content_type != "image/png":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PNG files are allowed")
    if file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File size exceeds 10MB limit")

@router.post("/signup")
async def signup(user: UserCreate):
    # 이메일 중복 체크
    query = User.__table__.select().where(User.email == user.email)
    exist = await database.fetch_one(query)
    if exist:
        raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다.")
    # 비밀번호 해시
    hashed_pw = get_password_hash(user.password)
    query = User.__table__.insert().values(email=user.email, password=hashed_pw)
    await database.execute(query)
    return BaseResponse(success=True, description="회원가입 성공", data=["OK"])


def get_userid_bytoken(token: str) -> str:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token missing")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    return user_id

@router.get("/users/me")
async def get_current_user(token: str = Depends(APIKeyHeader(name="access-token", auto_error=False))):
    user_id = get_userid_bytoken(token)

    # DB에서 사용자 조회
    query = User.__table__.select().where(User.id == int(user_id))
    user = await database.fetch_one(query)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Record를 dict로 변환
    user_dict = dict(user)

    return BaseResponse(success=True, description="조회 성공", data=[user_dict])

@router.post("/login")
async def login(user: UserLogin):
    query = User.__table__.select().where(User.email == user.email)
    db_user = await database.fetch_one(query)
    if not db_user or not verify_password(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    # JWT 발급
    access_token = create_access_token({"sub": str(db_user["id"])})
    refresh_token = create_refresh_token({"sub": str(db_user["id"])})

    return BaseResponse(success=True, description="로그인 성공", data=[{
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }])

@router.post("/upload")
async def upload(file: UploadFile = File(...), access_token: str = Security(APIKeyHeader(name='access-token'))):

    get_userid_bytoken(access_token)
    validate_file(file)

    query = (
        sqlalchemy.insert(Image)
        .values(user_id=get_userid_bytoken(access_token))
        .returning(Image)  # 삽입된 행 전체 반환
    )

    result = await database.fetch_one(query)

    inserted_data= dict(result)

    idx = inserted_data["id"]
    uuid_gt_filename = f"/{idx}/gt.png"
    uuid_lr_filename = f"/{idx}/lr.png"
    uuid_sr_filename = f"/{idx}/sr.png"
    uuid_sr_h_filename = f"/{idx}/sr_h.png"
    contents = await file.read()
    try:
        for path in [uuid_gt_filename, uuid_lr_filename, uuid_sr_filename, uuid_sr_h_filename]:
            s3.upload_fileobj(io.BytesIO(contents), BUCKET_NAME, path)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    return BaseResponse(success=True, description="생성 성공", data=[inserted_data])

@router.post("/validate")
async def validate(file: UploadFile = File(...), access_token: str = Security(APIKeyHeader(name='access-token'))):
    get_userid_bytoken(access_token)
    validate_file(file)

    # todo: input_data와 sr_h_data 데이터 검증 AI 서버 에서 검증 데이터 반환 2D image vector로 받음
    # todo : input_data에서 64bit(id) 뽑아내기 -> 64bit(id)에 해당하는 sr_h_data와 비교

    # todo : ai -> backend json {
    #   output_sr_h_data: "base64_encoded_image_string",
    # }



    return BaseResponse(success=True, description="검증 성공", data=[
        {
            "message": "검증 로직은 아직 구현되지 않았습니다.",
            "input_data": file.filename,  # 예시로 파일 이름 반환
            "64bit" : 1,
            "output_sr_h_data": "검증된 이미지 데이터"  # 실제 검증된 이미지 데이터는 AI 서버에서 받아와야 함
        }
    ]) # todo 프론트에 결과 반환하여 보여줌