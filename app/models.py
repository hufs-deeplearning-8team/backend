from datetime import datetime, timezone, timedelta
from enum import Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Float, Enum as SQLEnum, Text

Base = declarative_base()

# 한국 시간대 설정
KST = timezone(timedelta(hours=9))

def kst_now():
    """한국 시간으로 현재 시간 반환"""
    return datetime.now(KST)

class ProtectionAlgorithm(Enum):
    EditGuard = "EditGuard"

class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    api_key = Column(String(255), nullable=True, unique=True)
    time_created = Column(DateTime(timezone=True), default=kst_now)
    

class Image(Base):
    __tablename__ = "image"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    copyright = Column(String(255), nullable=True)
    protection_algorithm = Column(SQLEnum(ProtectionAlgorithm), nullable=True)
    use_openapi = Column(Boolean, nullable=False, default=False)
    time_created = Column(DateTime(timezone=True), default=kst_now)

class ValidationRecord(Base):
    __tablename__ = "validation_record"
    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    input_image_filename = Column(String(255), nullable=False)
    has_watermark = Column(Boolean, nullable=False, default=False)
    detected_watermark_image_id = Column(Integer, ForeignKey("image.id"), nullable=True)
    modification_rate = Column(Float, nullable=True)
    validation_algorithm = Column(SQLEnum(ProtectionAlgorithm), nullable=True)
    user_report_link = Column(String(2000), nullable=True)
    user_report_text = Column(Text, nullable=True)
    time_created = Column(DateTime(timezone=True), default=kst_now)