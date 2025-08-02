# 1. 기본 이미지로 python:3.11-slim-bookworm을 사용합니다.
FROM python:3.11-slim

# 빌드에 필요한 패키지 설치 및 uv 설치를 한 번에
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libmariadb-dev \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

# 3. 작업 디렉토리를 생성하고 이동합니다.
WORKDIR /app

# 4. 프로젝트의 의존성 정의 파일을 복사합니다.
COPY pyproject.toml uv.lock ./

# 5. uv를 사용하여 의존성을 설치합니다.
RUN uv sync --frozen --no-dev

# 6. 나머지 프로젝트 파일들을 복사합니다.
COPY . .

# 7. 컨테이너가 시작될 때 실행할 명령어를 설정합니다.
CMD ["uv", "run", "main.py"]