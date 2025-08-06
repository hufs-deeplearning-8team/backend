from datetime import datetime
from enum import Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Float, Enum as SQLEnum
from sqlalchemy.sql import func

Base = declarative_base()

class ProtectionAlgorithm(Enum):
    EditGuard = "EditGuard"
    OmniGuard = "OmniGuard"
    RobustWide = "RobustWide"

class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    time_created = Column(DateTime(timezone=True), server_default=func.now())
    

class Image(Base):
    __tablename__ = "image"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    copyright = Column(String(255), nullable=True)
    protection_algorithm = Column(SQLEnum(ProtectionAlgorithm), nullable=True)
    time_created = Column(DateTime(timezone=True), server_default=func.now())

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
    time_created = Column(DateTime(timezone=True), server_default=func.now())