# AEGIS OPEN API 문서

## 개요
AEGIS OPEN API는 API 키를 사용하여 이미지 생성(워터마크 적용) 및 검증 기능을 제공합니다.

## 인증 방식
- **Header**: `X-API-Key: {your_api_key}`
- **API Key Format**: `ak_` + 32자리 랜덤 문자열
- 예시: `X-API-Key: ak_AbCdEfGh12345678901234567890AbCd`

## 지원 알고리즘
- `EditGuard`: 조작된 영역을 95% 이상 정밀도로 탐지
- `RobustWide`: AI 편집 공격에 강력한 생존력을 가진 워터마크
- `FAKEFACE`: 얼굴 딥페이크 방지 알고리즘

---

## 1. 이미지 생성 (워터마크 적용)

### POST `/open/generate`

이미지에 워터마크를 적용하여 저작권을 보호합니다.

#### Request Headers
```
X-API-Key: ak_your_api_key_here
Content-Type: multipart/form-data
```

#### Request Body (Form Data)
| 필드명 | 타입 | 필수 | 설명 |
|--------|------|------|------|
| `file` | File | ✅ | 업로드할 PNG 파일 (최대 10MB) |
| `copyright` | String | ✅ | 저작권 정보 (최대 255자) |
| `protection_algorithm` | String | ✅ | 보호 알고리즘 (`EditGuard`, `RobustWide`, `FAKEFACE`) |

#### Response (200 OK)
```json
{
  "success": true,
  "description": "API를 통한 생성 성공",
  "data": [
    {
      "id": 123,
      "user_id": 456,
      "filename": "example.png",
      "copyright": "© 2025 Company Name",
      "protection_algorithm": "FAKEFACE",
      "time_created": "2025-01-20T10:30:00Z",
      "s3_paths": {
        "original": "https://s3.example.com/image/123/example_origi.png",
        "watermarked": "https://s3.example.com/image/123/example_wm.png"
      }
    }
  ]
}
```

#### Error Responses
- **400 Bad Request**: 잘못된 파일 형식 또는 크기 초과
- **401 Unauthorized**: 유효하지 않은 API 키
- **500 Internal Server Error**: 서버 오류

#### cURL 예시
```bash
curl -X POST "https://your-api-domain.com/open/generate" \
  -H "X-API-Key: ak_your_api_key_here" \
  -F "file=@/path/to/your/image.png" \
  -F "copyright=© 2025 My Company" \
  -F "protection_algorithm=FAKEFACE"
```

---

## 2. 이미지 검증

### POST `/open/verify`

이미지의 위변조 여부를 검증합니다.

#### Request Headers
```
X-API-Key: ak_your_api_key_here
Content-Type: multipart/form-data
```

#### Request Body (Form Data)
| 필드명 | 타입 | 필수 | 설명 |
|--------|------|------|------|
| `file` | File | ✅ | 검증할 PNG 파일 |
| `model` | String | ✅ | 보호 알고리즘 (`EditGuard`, `RobustWide`, `FAKEFACE`) |

#### Response (200 OK)
```json
{
  "success": true,
  "description": "API를 통한 이미지 위변조 검증이 완료되었습니다.",
  "data": [
    {
      "tampering_rate": 15.23,
      "ai_tampering_rate": 14.8,
      "tampered_regions_mask": "base64_encoded_mask_image_data",
      "original_image_id": 789
    }
  ]
}
```

#### Response 필드 설명
- `tampering_rate`: 계산된 변조율 (%)
- `ai_tampering_rate`: AI 서버 응답 변조율 (참고용)
- `tampered_regions_mask`: 변조된 영역을 표시하는 마스크 이미지 (Base64)
- `original_image_id`: 원본 이미지 ID

#### Error Responses
- **400 Bad Request**: 잘못된 파일 형식
- **401 Unauthorized**: 유효하지 않은 API 키
- **500 Internal Server Error**: 서버 오류

#### cURL 예시
```bash
curl -X POST "https://your-api-domain.com/open/verify" \
  -H "X-API-Key: ak_your_api_key_here" \
  -F "file=@/path/to/verify/image.png" \
  -F "model=FAKEFACE"
```

---

## JavaScript 예시

### 이미지 생성
```javascript
const generateImage = async (file, copyright, algorithm, apiKey) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('copyright', copyright);
  formData.append('protection_algorithm', algorithm);

  try {
    const response = await fetch('/open/generate', {
      method: 'POST',
      headers: {
        'X-API-Key': apiKey
      },
      body: formData
    });

    const result = await response.json();
    
    if (result.success) {
      console.log('생성 성공:', result.data[0]);
      return result.data[0];
    } else {
      throw new Error(result.description);
    }
  } catch (error) {
    console.error('생성 실패:', error);
    throw error;
  }
};
```

### 이미지 검증
```javascript
const verifyImage = async (file, model, apiKey) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('model', model);

  try {
    const response = await fetch('/open/verify', {
      method: 'POST',
      headers: {
        'X-API-Key': apiKey
      },
      body: formData
    });

    const result = await response.json();
    
    if (result.success) {
      console.log('검증 결과:', result.data[0]);
      return result.data[0];
    } else {
      throw new Error(result.description);
    }
  } catch (error) {
    console.error('검증 실패:', error);
    throw error;
  }
};
```

---

## 제한사항
- **파일 형식**: PNG만 지원
- **파일 크기**: 최대 10MB
- **API 키**: 회원가입 시 자동 발급, 각 사용자마다 고유한 키
- **요청 제한**: 서버 설정에 따라 달라질 수 있음

## 오류 코드 정리
| 상태 코드 | 설명 | 해결 방법 |
|-----------|------|----------|
| 400 | 잘못된 요청 (파일 형식, 크기, 알고리즘) | 요청 파라미터 확인 |
| 401 | 인증 실패 (잘못된 API 키) | API 키 확인 및 재발급 |
| 413 | 파일 크기 초과 | 파일 크기를 10MB 이하로 조정 |
| 500 | 서버 내부 오류 | 서버 관리자에게 문의 |

## 지원
기술적 문제가 있을 경우 개발팀에 문의해 주세요.