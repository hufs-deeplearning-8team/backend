#!/usr/bin/env python3
"""
간단한 RobustWide 검증 테스트
"""

import requests
from PIL import Image as PILImage
import io


def create_simple_test_image():
    """간단한 테스트 이미지 생성"""
    image = PILImage.new('RGB', (50, 50), (100, 150, 200))
    
    # PNG 바이트로 변환
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def test_validation():
    """검증 API 테스트"""
    print("🧪 RobustWide 검증 API 간단 테스트")
    
    try:
        # 테스트 이미지 생성
        image_bytes = create_simple_test_image()
        print(f"✅ 테스트 이미지 생성: {len(image_bytes)} bytes")
        
        # API 요청
        files = {
            'file': ('test.png', image_bytes, 'image/png')
        }
        
        data = {
            'validation_algorithm': 'RobustWide'
        }
        
        headers = {
            'X-API-Key': 'test_key'  # API Key 헤더 시도
        }
        
        print("📤 API 요청 전송...")
        response = requests.post(
            "http://localhost:8000/validate",
            files=files,
            data=data,
            headers=headers,
            timeout=10
        )
        
        print(f"📬 응답 상태: {response.status_code}")
        print(f"📝 응답 내용: {response.text[:500]}...")
        
        if response.status_code == 200:
            print("✅ API 호출 성공!")
            return True
        else:
            print(f"❌ API 호출 실패: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 테스트 실패: {str(e)}")
        return False


if __name__ == "__main__":
    test_validation()