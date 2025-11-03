"""
FastAPI 백그라운드 작업 관리자
더 간단하고 FastAPI 네이티브한 방식의 스케줄링
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class SimpleScheduler:
    """간단한 FastAPI 백그라운드 스케줄러"""
    
    def __init__(self):
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self.run_count = 0
    
    async def weekly_email_sender(self):
        """주간 이메일 발송 루프"""
        from app.services.validation_service import validation_service
        
        while self.running:
            try:
                now = datetime.now()
                
                # 일요일(6) 오전 9시인지 확인
                if now.weekday() == 6 and now.hour == 9 and now.minute < 5:
                    self.run_count += 1
                    logger.info(f"🚀 Starting weekly email reports #{self.run_count}...")
                    
                    start_time = datetime.now()
                    await validation_service.send_weekly_reports_to_all_users()
                    end_time = datetime.now()
                    duration = (end_time - start_time).total_seconds()
                    
                    self.last_run = end_time
                    logger.info(f"✅ Weekly email reports #{self.run_count} completed in {duration:.2f}s")
                    
                    # 이미 보냈으면 1시간 대기 (중복 방지)
                    await asyncio.sleep(3600)
                
                # 다음 실행 시간 계산
                self.next_run = self._get_next_sunday_9am()
                
                # 5분마다 체크
                await asyncio.sleep(300)
                
            except Exception as e:
                logger.error(f"❌ Error in weekly email sender: {str(e)}")
                await asyncio.sleep(300)  # 에러 시 5분 후 재시도
    
    async def start(self):
        """스케줄러 시작"""
        if self.running:
            logger.warning("Scheduler is already running")
            return
        
        self.running = True
        self.task = asyncio.create_task(self.weekly_email_sender())
        logger.info("✅ Simple scheduler started")
    
    async def stop(self):
        """스케줄러 중지"""
        self.running = False
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Simple scheduler stopped")
    
    def get_status(self) -> dict:
        """스케줄러 상태"""
        now = datetime.now()
        
        return {
            "running": self.running,
            "task_alive": self.task and not self.task.done() if self.task else False,
            "run_count": self.run_count,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "seconds_until_next": (self.next_run - now).total_seconds() if self.next_run and self.next_run > now else 0,
            "next_sunday_9am": self._get_next_sunday_9am().isoformat(),
            "current_time": now.isoformat()
        }
    
    def _get_next_sunday_9am(self) -> datetime:
        """다음 일요일 9시 계산"""
        now = datetime.now()
        days_until_sunday = (6 - now.weekday()) % 7
        if days_until_sunday == 0 and now.hour >= 9:
            days_until_sunday = 7
        
        next_sunday = now + timedelta(days=days_until_sunday)
        return next_sunday.replace(hour=9, minute=0, second=0, microsecond=0)


# 전역 인스턴스
simple_scheduler = SimpleScheduler()


# FastAPI BackgroundTasks를 사용한 즉시 실행 함수들
async def send_immediate_weekly_report():
    """즉시 주간 리포트 발송 (API 호출용)"""
    from app.services.validation_service import validation_service
    
    try:
        logger.info("🚀 Immediate weekly report requested")
        result = await validation_service.send_weekly_reports_to_all_users()
        logger.info(f"✅ Immediate weekly report completed: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ Error in immediate weekly report: {str(e)}")
        return False


async def send_test_email_to_admin():
    """관리자에게 테스트 이메일 발송"""
    from app.services.email_service import email_service
    
    try:
        subject = "🔧 Aegis 시스템 테스트"
        body = f"""
        <h2>Aegis 이메일 시스템 테스트</h2>
        <p>이 메일은 수동 테스트 요청으로 발송되었습니다.</p>
        <p><strong>발송 시간:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        """
        
        result = await email_service.send_email(
            "kisiaaegis@gmail.com", 
            subject, 
            body, 
            is_html=True
        )
        
        logger.info(f"✅ Test email sent: {result}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Error sending test email: {str(e)}")
        return False