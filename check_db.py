#!/usr/bin/env python3
"""
DB에 있는 이미지 목록 확인
"""

import asyncio
import sys
import os

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db import database
from app.models import Image
import sqlalchemy


async def check_images():
    """DB에 있는 이미지들 확인"""
    try:
        await database.connect()
        
        # 이미지 목록 조회
        query = sqlalchemy.select(Image.id, Image.filename, Image.protection_algorithm, Image.time_created).order_by(Image.id.desc()).limit(10)
        images = await database.fetch_all(query)
        
        print(f"DB에 저장된 이미지 수: {len(images)}")
        print("=" * 50)
        
        for image in images:
            print(f"ID: {image['id']}")
            print(f"파일명: {image['filename']}")
            print(f"보호 알고리즘: {image['protection_algorithm']}")
            print(f"생성일: {image['time_created']}")
            print("-" * 30)
        
        await database.disconnect()
        return len(images) > 0
        
    except Exception as e:
        print(f"DB 조회 실패: {str(e)}")
        return False


async def main():
    """메인 함수"""
    print("🔍 DB 이미지 목록 확인")
    
    has_images = await check_images()
    
    if has_images:
        print("\n✅ DB에 이미지가 있습니다. RobustWide 테스트 가능합니다.")
    else:
        print("\n❌ DB에 이미지가 없습니다. 먼저 이미지를 업로드해야 합니다.")


if __name__ == "__main__":
    asyncio.run(main())