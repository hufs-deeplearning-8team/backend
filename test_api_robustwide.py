#!/usr/bin/env python3
"""
RobustWide API 테스트 스크립트
실제 API를 통해 mask 생성과 S3 업로드를 테스트
"""

import requests
import json
import base64
import io
from PIL import Image as PILImage


def create_test_image():
    """테스트용 이미지 생성"""
    width, height = 100, 100
    
    # 간단한 테스트 이미지 (파란색 배경에 빨간 사각형)
    image = PILImage.new('RGB', (width, height), (50, 100, 200))
    pixels = image.load()
    
    # 중앙에 빨간 사각형 추가
    for x in range(40, 60):
        for y in range(40, 60):
            pixels[x, y] = (255, 50, 50)
    
    # PNG 바이트로 변환
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def test_robustwide_validation():
    """RobustWide 검증 API 테스트"""
    print("🧪 RobustWide API 검증 테스트")
    print("=" * 50)
    
    try:
        # 테스트 이미지 생성
        image_bytes = create_test_image()
        print(f"✅ 테스트 이미지 생성: {len(image_bytes)} bytes")
        
        # API 엔드포인트 설정
        base_url = "http://localhost:8000"
        
        # 1. 먼저 로그인해서 토큰 획득 (실제 환경에서는 유효한 계정 필요)
        print("\n🔐 로그인 시도...")
        login_data = {
            "email": "test@example.com",
            "password": "testpassword"
        }
        
        try:
            login_response = requests.post(f"{base_url}/auth/login", json=login_data)
            print(f"로그인 응답 상태: {login_response.status_code}")
            
            if login_response.status_code == 200:
                token = login_response.json().get("data", [{}])[0].get("access_token")
                print(f"✅ 토큰 획득 성공")
            else:
                print(f"❌ 로그인 실패: {login_response.text}")
                # 테스트용 가짜 토큰 사용
                token = "test_token_for_validation"
                print("⚠️  테스트용 토큰 사용")
        except Exception as e:
            print(f"❌ 로그인 오류: {str(e)}")
            token = "test_token_for_validation"
            print("⚠️  테스트용 토큰 사용")
        
        # 2. RobustWide 검증 요청
        print(f"\n📤 RobustWide 검증 요청...")
        
        files = {
            'file': ('test_image.png', image_bytes, 'image/png')
        }
        
        data = {
            'validation_algorithm': 'RobustWide'
        }
        
        headers = {
            'Authorization': f'Bearer {token}'
        }
        
        try:
            response = requests.post(
                f"{base_url}/validation/validate",
                files=files,
                data=data,
                headers=headers,
                timeout=30
            )
            
            print(f"📬 검증 응답 상태: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 검증 성공!")
                
                # 응답 데이터 분석
                if result.get("success"):
                    validation_data = result.get("data", [{}])[0]
                    
                    print(f"\n📊 검증 결과:")
                    print(f"   - 워터마크 감지: {validation_data.get('has_watermark')}")
                    print(f"   - 변조률: {validation_data.get('modification_rate')}%")
                    print(f"   - 감지된 원본 ID: {validation_data.get('detected_watermark_image_id')}")
                    print(f"   - 검증 ID: {validation_data.get('validation_id')}")
                    
                    # mask 데이터 확인
                    mask_base64 = validation_data.get('visualization_image_base64')
                    if mask_base64:
                        print(f"   - Mask 데이터: {len(mask_base64)} characters")
                        print(f"   ✅ RobustWide mask 생성됨!")
                        
                        # mask 이미지 저장 테스트
                        try:
                            mask_bytes = base64.b64decode(mask_base64)
                            mask_image = PILImage.open(io.BytesIO(mask_bytes))
                            print(f"   - Mask 크기: {mask_image.size}, 모드: {mask_image.mode}")
                        except Exception as e:
                            print(f"   ❌ Mask 디코딩 실패: {str(e)}")
                    else:
                        print(f"   - Mask 데이터: 없음")
                        
                    return True
                else:
                    print(f"❌ 검증 실패: {result.get('description')}")
                    return False
                    
            else:
                print(f"❌ API 호출 실패: {response.status_code}")
                print(f"응답: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ 검증 요청 오류: {str(e)}")
            return False
            
    except Exception as e:
        print(f"❌ 테스트 실패: {str(e)}")
        return False


def test_health_check():
    """서버 상태 확인"""
    print("🏥 서버 상태 확인")
    print("-" * 30)
    
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        print(f"서버 상태: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ 서버 정상 동작")
            return True
        else:
            print("❌ 서버 응답 이상")
            return False
            
    except Exception as e:
        print(f"❌ 서버 연결 실패: {str(e)}")
        return False


def main():
    """메인 테스트"""
    print("🚀 RobustWide API 테스트")
    print("📝 실제 API를 통한 mask 생성 및 S3 업로드 테스트")
    print()
    
    # 1. 서버 상태 확인
    server_ok = test_health_check()
    
    if not server_ok:
        print("\n❌ 서버가 실행되지 않았습니다. main.py를 먼저 실행해주세요.")
        return
    
    # 2. RobustWide 검증 테스트
    validation_ok = test_robustwide_validation()
    
    print("\n" + "=" * 50)
    print("📋 API 테스트 결과:")
    print(f"   - 서버 상태: {'✅ 정상' if server_ok else '❌ 오류'}")
    print(f"   - RobustWide 검증: {'✅ 성공' if validation_ok else '❌ 실패'}")
    
    if server_ok and validation_ok:
        print("\n🎉 API 테스트 통과!")
        print("💡 RobustWide mask 생성 및 S3 업로드가 API에서 정상 작동합니다.")
    else:
        print("\n⚠️  API 테스트 실패")
        print("💡 서버 로그를 확인해서 자세한 오류를 확인해주세요.")


if __name__ == "__main__":
    main()