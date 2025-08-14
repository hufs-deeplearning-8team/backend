#!/usr/bin/env python3
"""
간단한 mask 생성 테스트 (의존성 최소화)
"""

import asyncio
import base64
import io
from PIL import Image as PILImage
import numpy as np


async def create_difference_mask(input_image_bytes: bytes, original_sr_h_bytes: bytes) -> tuple[str, float]:
    """입력 이미지와 원본 sr_h 이미지의 픽셀 차이를 기반으로 mask 생성"""
    try:
        # 입력 이미지와 원본 sr_h 이미지 로드
        input_image = PILImage.open(io.BytesIO(input_image_bytes))
        original_image = PILImage.open(io.BytesIO(original_sr_h_bytes))
        
        # 이미지 크기 맞춤
        if input_image.size != original_image.size:
            input_image = input_image.resize(original_image.size)
        
        # RGB 모드로 통일
        if input_image.mode != 'RGB':
            input_image = input_image.convert('RGB')
        if original_image.mode != 'RGB':
            original_image = original_image.convert('RGB')
        
        # numpy 배열로 변환
        input_array = np.array(input_image)
        original_array = np.array(original_image)
        
        # 픽셀 차이 계산 (절댓값 차이의 합)
        diff = np.abs(input_array.astype(np.float32) - original_array.astype(np.float32))
        
        # 임계값을 넘는 차이가 있는 픽셀을 변조된 것으로 판단
        threshold = 10  # RGB 값 차이 임계값 (조정 가능)
        diff_magnitude = np.sqrt(np.sum(diff ** 2, axis=2))  # RGB 차이의 크기
        
        # 변조된 픽셀 마스크 (차이가 임계값을 넘으면 True)
        tampered_mask = diff_magnitude > threshold
        
        # 변조률 계산
        total_pixels = tampered_mask.size
        tampered_pixels = np.sum(tampered_mask)
        tampering_rate = (tampered_pixels / total_pixels * 100) if total_pixels > 0 else 0.0
        
        # 마스크 이미지 생성 (변조된 부분은 빨간색, 정상 부분은 투명)
        mask_image = np.zeros((*tampered_mask.shape, 4), dtype=np.uint8)  # RGBA
        mask_image[tampered_mask] = [255, 0, 0, 180]  # 빨간색, 반투명
        mask_image[~tampered_mask] = [0, 0, 0, 0]  # 투명
        
        # PIL 이미지로 변환
        mask_pil = PILImage.fromarray(mask_image, mode='RGBA')
        
        # base64로 인코딩
        mask_buffer = io.BytesIO()
        mask_pil.save(mask_buffer, format='PNG')
        mask_base64 = base64.b64encode(mask_buffer.getvalue()).decode('utf-8')
        
        print(f"✅ RobustWide mask 생성 완료: 변조률 {tampering_rate:.2f}% ({tampered_pixels}/{total_pixels} 픽셀)")
        
        return mask_base64, tampering_rate
        
    except Exception as e:
        print(f"❌ RobustWide mask 생성 중 오류: {str(e)}")
        return "", 0.0


async def create_test_images():
    """테스트용 이미지 생성"""
    width, height = 200, 200
    
    # 원본 이미지 (파란색)
    original_image = PILImage.new('RGB', (width, height), (50, 100, 200))
    
    # 변조된 이미지 (일부를 다른 색으로 변경)
    modified_image = original_image.copy()
    pixels = modified_image.load()
    
    # 여러 영역을 변조
    # 1. 중앙 30x30 영역을 빨간색으로
    for x in range(85, 115):
        for y in range(85, 115):
            pixels[x, y] = (255, 50, 50)
    
    # 2. 우상단 20x20 영역을 노란색으로
    for x in range(160, 180):
        for y in range(20, 40):
            pixels[x, y] = (255, 255, 50)
    
    # 3. 좌하단 25x25 영역을 초록색으로
    for x in range(20, 45):
        for y in range(160, 185):
            pixels[x, y] = (50, 255, 50)
    
    # 이미지를 bytes로 변환
    original_buffer = io.BytesIO()
    original_image.save(original_buffer, format='PNG')
    original_bytes = original_buffer.getvalue()
    
    modified_buffer = io.BytesIO()
    modified_image.save(modified_buffer, format='PNG')
    modified_bytes = modified_buffer.getvalue()
    
    # 테스트용으로 로컬에 저장
    original_image.save('/tmp/test_original.png')
    modified_image.save('/tmp/test_modified.png')
    print(f"📁 테스트 이미지 저장: /tmp/test_original.png, /tmp/test_modified.png")
    
    return original_bytes, modified_bytes


async def test_mask_generation():
    """mask 생성 테스트"""
    print("🧪 RobustWide mask 생성 테스트 시작")
    print("=" * 50)
    
    try:
        # 테스트 이미지 생성
        original_bytes, modified_bytes = await create_test_images()
        print(f"✅ 테스트 이미지 생성 완료")
        print(f"   - 원본 크기: {len(original_bytes)} bytes")
        print(f"   - 변조 크기: {len(modified_bytes)} bytes")
        
        # mask 생성
        mask_base64, tampering_rate = await create_difference_mask(modified_bytes, original_bytes)
        
        if mask_base64:
            print(f"\n✅ Mask 생성 성공!")
            print(f"   - 변조률: {tampering_rate:.2f}%")
            print(f"   - Base64 길이: {len(mask_base64)} characters")
            
            # mask 이미지 디코딩 및 저장
            try:
                mask_bytes = base64.b64decode(mask_base64)
                mask_image = PILImage.open(io.BytesIO(mask_bytes))
                mask_image.save('/tmp/test_robustwide_mask.png')
                print(f"   - Mask 저장: /tmp/test_robustwide_mask.png")
                print(f"   - Mask 크기: {mask_image.size}, 모드: {mask_image.mode}")
                
                # 투명도가 있는 부분과 빨간색 부분 확인
                mask_array = np.array(mask_image)
                red_pixels = np.sum((mask_array[:, :, 0] > 200) & (mask_array[:, :, 3] > 100))  # 빨간색이면서 불투명
                total_pixels = mask_array.shape[0] * mask_array.shape[1]
                mask_coverage = (red_pixels / total_pixels) * 100
                
                print(f"   - 빨간색 픽셀: {red_pixels}/{total_pixels} ({mask_coverage:.2f}%)")
                
                return True
                
            except Exception as e:
                print(f"❌ Mask 디코딩 실패: {str(e)}")
                return False
        else:
            print(f"❌ Mask 생성 실패 (빈 결과)")
            return False
            
    except Exception as e:
        print(f"❌ 테스트 실패: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_identical_images():
    """동일한 이미지로 테스트 (변조률 0%여야 함)"""
    print("\n🔍 동일 이미지 테스트 (변조률 0% 예상)")
    print("-" * 30)
    
    # 동일한 이미지 생성
    width, height = 100, 100
    test_image = PILImage.new('RGB', (width, height), (100, 150, 200))
    
    buffer = io.BytesIO()
    test_image.save(buffer, format='PNG')
    image_bytes = buffer.getvalue()
    
    # 동일한 이미지끼리 비교
    mask_base64, tampering_rate = await create_difference_mask(image_bytes, image_bytes)
    
    print(f"   - 변조률: {tampering_rate:.2f}% (0%이어야 함)")
    print(f"   - Mask 데이터: {'있음' if mask_base64 else '없음'}")
    
    if tampering_rate == 0.0:
        print("   ✅ 정상: 동일 이미지는 변조률 0%")
        return True
    else:
        print("   ❌ 오류: 동일 이미지인데 변조 감지됨")
        return False


async def main():
    """메인 테스트"""
    print("🚀 RobustWide Mask 생성 단독 테스트")
    print("📝 이 테스트는 백엔드 픽셀 비교 mask 생성 로직을 검증합니다")
    print()
    
    # 테스트 실행
    test1_ok = await test_mask_generation()
    test2_ok = await test_identical_images()
    
    print("\n" + "=" * 50)
    print("📋 테스트 결과:")
    print(f"   - 변조 이미지 mask 생성: {'✅ 성공' if test1_ok else '❌ 실패'}")
    print(f"   - 동일 이미지 처리: {'✅ 성공' if test2_ok else '❌ 실패'}")
    
    if test1_ok and test2_ok:
        print("\n🎉 모든 테스트 통과!")
        print("💡 RobustWide 픽셀 비교 mask 생성이 정상 작동합니다.")
        print("📁 생성된 파일들:")
        print("   - /tmp/test_original.png (원본)")
        print("   - /tmp/test_modified.png (변조된 이미지)")
        print("   - /tmp/test_robustwide_mask.png (생성된 mask)")
    else:
        print("\n⚠️  일부 테스트 실패")


if __name__ == "__main__":
    asyncio.run(main())