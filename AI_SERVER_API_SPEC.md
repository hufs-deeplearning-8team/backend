# AI 서버 API 명세서

이 문서는 Aegis 백엔드와 AI 서버 간의 통신을 위한 API 명세서입니다.

## 개요

- **목적**: 이미지 워터마크 검증 및 변조 감지
- **통신 방식**: HTTP REST API
- **데이터 형식**: JSON
- **이미지 전송**: Base64 인코딩

## API 엔드포인트

### 1. 이미지 검증 API

#### POST /validate-image

이미지를 분석하여 워터마크 존재 여부와 변조 정도를 검증합니다.

**요청 (Request)**

```http
POST /validate-image
Content-Type: application/json

{
  "input_image_base64": "string",
  "filename": "string"
}
```

**요청 스키마**
```json
{
  "input_image_base64": {
    "type": "string",
    "description": "검증할 이미지의 Base64 인코딩 데이터",
    "required": true
  },
  "filename": {
    "type": "string", 
    "description": "업로드된 파일명",
    "required": true,
    "example": "test_image.png"
  }
}
```

**응답 (Response)**

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "has_watermark": true,
  "detected_watermark_image_id": 123,
  "modification_rate": 0.15,
  "confidence_score": 0.92,
  "visualization_image_base64": "iVBORw0KGgoAAAANSUhEUgAAA..."
}
```

**응답 스키마**
```json
{
  "has_watermark": {
    "type": "boolean",
    "description": "워터마크 존재 여부"
  },
  "detected_watermark_image_id": {
    "type": "integer",
    "description": "감지된 워터마크 원본 이미지 ID (워터마크가 있을 경우)",
    "nullable": true
  },
  "modification_rate": {
    "type": "number",
    "description": "이미지 변조율 (0.0 ~ 1.0)",
    "nullable": true,
    "minimum": 0.0,
    "maximum": 1.0
  },
  "confidence_score": {
    "type": "number", 
    "description": "AI 모델의 신뢰도 점수 (0.0 ~ 1.0)",
    "nullable": true,
    "minimum": 0.0,
    "maximum": 1.0
  },
  "visualization_image_base64": {
    "type": "string",
    "description": "변조 부분을 시각화한 이미지 (Base64, 변조가 감지된 경우에만)",
    "nullable": true
  }
}
```

## 에러 응답

모든 API는 오류 발생 시 다음과 같은 형식으로 응답합니다:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "string",
  "message": "string",
  "code": "string"
}
```

**일반적인 에러 코드**
- `400 Bad Request`: 잘못된 요청 형식
- `413 Payload Too Large`: 이미지 크기 초과 
- `415 Unsupported Media Type`: 지원하지 않는 파일 형식
- `500 Internal Server Error`: AI 서버 내부 오류

## 데이터 형식 요구사항

### 이미지 요구사항
- **형식**: PNG 파일만 지원
- **최대 크기**: 10MB
- **인코딩**: Base64

### Base64 인코딩 형식
```
data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAA...
```
또는
```
iVBORw0KGgoAAAANSUhEUgAAA...
```

## 사용 예시

### Python 클라이언트 예시

```python
import base64
import requests

# 이미지 파일을 Base64로 인코딩
with open("test_image.png", "rb") as image_file:
    encoded_string = base64.b64encode(image_file.read()).decode()

# API 요청
payload = {
    "input_image_base64": encoded_string,
    "filename": "test_image.png"
}

response = requests.post(
    "http://ai-server:8080/validate-image",
    json=payload
)

if response.status_code == 200:
    result = response.json()
    print(f"워터마크 존재: {result['has_watermark']}")
    print(f"변조율: {result['modification_rate']}")
    print(f"신뢰도: {result['confidence_score']}")
else:
    print(f"오류: {response.status_code} - {response.text}")
```

### JavaScript 클라이언트 예시

```javascript
// 파일을 Base64로 변환
function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => resolve(reader.result.split(',')[1]);
        reader.onerror = error => reject(error);
    });
}

// API 호출
async function validateImage(file) {
    try {
        const base64Data = await fileToBase64(file);
        
        const response = await fetch('http://ai-server:8080/validate-image', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                input_image_base64: base64Data,
                filename: file.name
            })
        });
        
        if (response.ok) {
            const result = await response.json();
            console.log('검증 결과:', result);
            return result;
        } else {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
    } catch (error) {
        console.error('이미지 검증 오류:', error);
        throw error;
    }
}
```

## 백엔드 통합 정보

현재 Aegis 백엔드의 `app/services/validation_service.py`에서 `simulate_ai_validation` 함수가 AI 서버를 시뮬레이션하고 있습니다. 실제 AI 서버 구현 시 이 함수를 실제 HTTP 클라이언트 호출로 대체해야 합니다.

### 통합 시 변경사항
1. `simulate_ai_validation` 함수를 실제 AI 서버 API 호출로 교체
2. AI 서버 URL 설정을 환경변수로 관리
3. 타임아웃 및 재시도 로직 구현
4. 에러 핸들링 강화

## 성능 고려사항

- **응답 시간**: 일반적으로 1-5초 내 응답 권장
- **동시 요청**: AI 서버의 GPU 리소스에 따라 제한
- **이미지 크기**: 큰 이미지일수록 처리 시간 증가
- **캐싱**: 동일한 이미지에 대한 결과 캐싱 고려

## 보안 고려사항

- AI 서버와의 통신은 내부 네트워크에서만 허용
- 필요시 API 키 인증 추가 고려
- 이미지 데이터 로깅 시 개인정보 보호 준수