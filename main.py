import os
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from app.db_lifespan import lifespan
from api import router
from fastapi.middleware.cors import CORSMiddleware
import traceback
import logging

# 스케줄러 관련 import
from app.background_tasks import simple_scheduler, send_immediate_weekly_report, send_test_email_to_admin
from fastapi import BackgroundTasks
from app.services.storage_service import storage_service

app = FastAPI(
    title="Aegis Backend API",
    description="이미지 업로드 및 저작권 보호를 위한 백엔드 API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)
# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js 개발 서버
        "https://aegis.gdgoc.com"  # 프로덕션 도메인
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"Error: {str(exc)}")
    print(f"Traceback: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"}
    )

app.include_router(router)

if storage_service.is_mock:
    app.mount(
        "/image",
        StaticFiles(directory=storage_service.local_image_dir),
        name="mock-image",
    )
    app.mount(
        "/record",
        StaticFiles(directory=storage_service.local_record_dir),
        name="mock-record",
    )

    @app.get("/images/{legacy_path:path}")
    async def serve_legacy_mock_image(legacy_path: str):
        """기존 S3 경로 형식을 사용하는 요청을 로컬 파일로 매핑"""
        relative_path = legacy_path.lstrip("/")

        if not relative_path or not (
            relative_path.startswith("image/") or relative_path.startswith("record/")
        ):
            raise HTTPException(status_code=404, detail="지원하지 않는 경로 형식입니다.")

        file_path = storage_service.resolve_local_file(relative_path)

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="요청한 파일을 찾을 수 없습니다.")

        return FileResponse(file_path)

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 스케줄러는 lifespan에서 관리됨

# 관리자용 API 엔드포인트들
@app.get("/admin/scheduler-status")
async def get_scheduler_status():
    """스케줄러 상태 조회 (관리자용)"""
    return {
        "simple_scheduler": simple_scheduler.get_status()
    }

@app.post("/admin/send-weekly-report")
async def manual_weekly_report(background_tasks: BackgroundTasks):
    """수동으로 주간 리포트 발송 (관리자용)"""
    background_tasks.add_task(send_immediate_weekly_report)
    return {"message": "주간 리포트 발송이 백그라운드에서 시작되었습니다."}

@app.post("/admin/send-test-email")
async def manual_test_email(background_tasks: BackgroundTasks):
    """테스트 이메일 발송 (관리자용)"""
    background_tasks.add_task(send_test_email_to_admin)
    return {"message": "테스트 이메일 발송이 백그라운드에서 시작되었습니다."}

# cors 해결

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="debug")
