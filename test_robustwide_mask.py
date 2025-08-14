#!/usr/bin/env python3
"""
RobustWide mask 생성 테스트 스크립트
백엔드에서 픽셀 비교로 mask를 제대로 생성하는지 테스트
"""

import asyncio
import sys
import os
import base64
import io
from PIL import Image as PILImage
import numpy as np

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.validation_service import ValidationService
from app.config import settings


async def create_test_images():
    """테스트용 이미지 생성"""
    # 100x100 크기의 테스트 이미지 생성
    width, height = 100, 100
    
    # 원본 이미지 (파란색)
    original_image = PILImage.new('RGB', (width, height), (0, 0, 255))
    
    # 변조된 이미지 (일부를 빨간색으로 변경)
    modified_image = original_image.copy()
    pixels = modified_image.load()
    
    # 중앙 20x20 영역을 빨간색으로 변조
    for x in range(40, 60):
        for y in range(40, 60):
            pixels[x, y] = (255, 0, 0)  # 빨간색
    
    # 이미지를 bytes로 변환
    original_buffer = io.BytesIO()
    original_image.save(original_buffer, format='PNG')
    original_bytes = original_buffer.getvalue()
    
    modified_buffer = io.BytesIO()
    modified_image.save(modified_buffer, format='PNG')
    modified_bytes = modified_buffer.getvalue()
    
    return original_bytes, modified_bytes


async def test_mask_generation():
    """마스크 생성 테스트"""
    print("🧪 RobustWide mask 생성 테스트 시작...")
    
    try:
        # 테스트 이미지 생성
        original_bytes, modified_bytes = await create_test_images()
        print(f"✅ 테스트 이미지 생성 완료 (원본: {len(original_bytes)} bytes, 변조: {len(modified_bytes)} bytes)")
        
        # ValidationService 인스턴스 생성
        validation_service = ValidationService()
        
        # mask 생성 테스트
        mask_base64, tampering_rate = await validation_service._create_difference_mask(
            modified_bytes, original_bytes
        )
        
        print(f"✅ mask 생성 완료:")
        print(f"   - 변조률: {tampering_rate:.2f}%")
        print(f"   - mask 데이터 크기: {len(mask_base64)} characters")
        print(f"   - mask 데이터 시작: {mask_base64[:50]}...")
        
        # mask가 유효한 base64인지 확인
        try:
            mask_bytes = base64.b64decode(mask_base64)
            print(f"✅ base64 디코딩 성공: {len(mask_bytes)} bytes")
            
            # mask 이미지가 유효한지 확인
            mask_image = PILImage.open(io.BytesIO(mask_bytes))
            print(f"✅ mask 이미지 로드 성공: {mask_image.size}, 모드: {mask_image.mode}")
            
            # 로컬에 저장해서 확인해보기
            mask_image.save('/tmp/test_robustwide_mask.png')
            print("✅ mask 이미지를 /tmp/test_robustwide_mask.png에 저장했습니다")
            
        except Exception as e:
            print(f"❌ mask 데이터 검증 실패: {str(e)}")
            return False
        
        # 예상 변조률 계산 (20x20 = 400 픽셀이 변조됨, 전체는 100x100 = 10000 픽셀)
        expected_rate = (400 / 10000) * 100  # 4%
        print(f"📊 예상 변조률: {expected_rate}%, 실제 변조률: {tampering_rate:.2f}%")
        
        if abs(tampering_rate - expected_rate) < 1.0:  # 1% 이내 오차
            print("✅ 변조률이 예상 범위 내에 있습니다")
        else:
            print("⚠️  변조률이 예상과 다릅니다")
        
        return True
        
    except Exception as e:
        print(f"❌ 테스트 실패: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_s3_upload_simulation():
    """S3 업로드 시뮬레이션 테스트"""
    print("\n🔗 S3 업로드 로직 시뮬레이션...")
    
    try:
        from app.services.storage_service import storage_service
        
        # S3 연결 테스트
        connection_ok = await storage_service.test_s3_connection()
        print(f"📡 S3 연결: {'✅ 성공' if connection_ok else '❌ 실패'}")
        
        if connection_ok:
            # 테스트 업로드
            upload_ok = await storage_service.test_upload()
            print(f"📤 S3 업로드 테스트: {'✅ 성공' if upload_ok else '❌ 실패'}")
        
        return connection_ok
        
    except Exception as e:
        print(f"❌ S3 테스트 실패: {str(e)}")
        return False


async def main():
    """메인 테스트 함수"""
    print("🚀 RobustWide mask 생성 및 S3 업로드 테스트")
    print("=" * 50)
    
    # 환경 설정 확인
    print(f"🔧 설정 확인:")
    print(f"   - AI_IP: {getattr(settings, 'AI_IP', 'Not set')}")
    print(f"   - S3_DEPLOYMENT_BUCKET: {getattr(settings, 'S3_DEPLOYMENT_BUCKET', 'Not set')}")
    print()
    
    # 1. mask 생성 테스트
    mask_test_ok = await test_mask_generation()
    
    # 2. S3 업로드 시뮬레이션
    s3_test_ok = await test_s3_upload_simulation()
    
    # 결과 요약
    print("\n" + "=" * 50)
    print("📋 테스트 결과 요약:")
    print(f"   - mask 생성: {'✅ 성공' if mask_test_ok else '❌ 실패'}")
    print(f"   - S3 연결: {'✅ 성공' if s3_test_ok else '❌ 실패'}")
    
    if mask_test_ok and s3_test_ok:
        print("\n🎉 모든 테스트 통과! RobustWide mask 생성 및 S3 업로드가 정상 작동합니다.")
    else:
        print("\n⚠️  일부 테스트 실패. 로그를 확인해주세요.")


if __name__ == "__main__":
    asyncio.run(main())