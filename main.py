import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.db_lifespan import lifespan
from api import router
from fastapi.middleware.cors import CORSMiddleware
import traceback

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

# cors 해결

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="debug")