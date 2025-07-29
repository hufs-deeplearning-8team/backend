from databases import Database
from sqlalchemy import create_engine, MetaData
from app.models import Base
from app.config import ASYNC_DATABASE_URL, SYNC_DATABASE_URL

database = Database(ASYNC_DATABASE_URL)
metadata = MetaData()

# 테이블 자동 생성 (동기)
engine = create_engine(SYNC_DATABASE_URL)
Base.metadata.drop_all(bind=engine)      # 모든 테이블 삭제
Base.metadata.create_all(bind=engine)    # 모든 테이블 새로 생성