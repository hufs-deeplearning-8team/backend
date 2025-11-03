import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
import threading
import time

logger = logging.getLogger(__name__)


class BackgroundScheduler:
    """백그라운드에서 실행되는 작업 스케줄러"""
    
    def __init__(self):
        self.tasks = []
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
    
    def add_weekly_task(self, func, day_of_week: int = 6, hour: int = 9, minute: int = 0):
        """
        주간 반복 작업 추가
        day_of_week: 0=월요일, 1=화요일, ..., 6=일요일
        hour: 실행할 시간 (0-23)
        minute: 실행할 분 (0-59)
        """
        task = {
            'func': func,
            'type': 'weekly',
            'day_of_week': day_of_week,
            'hour': hour,
            'minute': minute,
            'last_run': None
        }
        self.tasks.append(task)
        logger.info(f"Weekly task added: {func.__name__} - Every {['월','화','수','목','금','토','일'][day_of_week]} {hour:02d}:{minute:02d}")
    
    def add_daily_task(self, func, hour: int = 9, minute: int = 0):
        """
        일간 반복 작업 추가
        hour: 실행할 시간 (0-23)
        minute: 실행할 분 (0-59)
        """
        task = {
            'func': func,
            'type': 'daily',
            'hour': hour,
            'minute': minute,
            'last_run': None
        }
        self.tasks.append(task)
        logger.info(f"Daily task added: {func.__name__} - Every day {hour:02d}:{minute:02d}")
    
    def add_interval_task(self, func, minutes: int = 1):
        """
        간격 반복 작업 추가 (테스트용)
        minutes: 실행 간격 (분)
        """
        task = {
            'func': func,
            'type': 'interval',
            'interval_minutes': minutes,
            'last_run': None
        }
        self.tasks.append(task)
        logger.info(f"Interval task added: {func.__name__} - Every {minutes} minutes")
    
    def should_run_task(self, task: dict) -> bool:
        """작업 실행 여부 확인"""
        now = datetime.now()
        
        if task['type'] == 'weekly':
            # 지정된 요일이고 지정된 시간인지 확인
            if now.weekday() != task['day_of_week']:
                return False
            
            target_time = now.replace(hour=task['hour'], minute=task['minute'], second=0, microsecond=0)
            
            # 현재 시간이 target_time 이후이고, 아직 오늘 실행되지 않았다면 실행
            if now >= target_time:
                if task['last_run'] is None:
                    return True
                
                # 마지막 실행이 오늘이 아니라면 실행
                last_run_date = task['last_run'].date() if task['last_run'] else None
                if last_run_date != now.date():
                    return True
        
        elif task['type'] == 'daily':
            target_time = now.replace(hour=task['hour'], minute=task['minute'], second=0, microsecond=0)
            
            # 현재 시간이 target_time 이후이고, 아직 오늘 실행되지 않았다면 실행
            if now >= target_time:
                if task['last_run'] is None:
                    return True
                
                # 마지막 실행이 오늘이 아니라면 실행
                last_run_date = task['last_run'].date() if task['last_run'] else None
                if last_run_date != now.date():
                    return True
        
        elif task['type'] == 'interval':
            # 간격 작업 처리
            if task['last_run'] is None:
                return True
            
            # 마지막 실행으로부터 지정된 분이 지났는지 확인
            interval = timedelta(minutes=task['interval_minutes'])
            if now >= task['last_run'] + interval:
                return True
        
        return False
    
    async def run_task(self, task: dict):
        """작업 실행"""
        try:
            logger.info(f"Running scheduled task: {task['func'].__name__}")
            
            # 비동기 함수인지 확인
            if asyncio.iscoroutinefunction(task['func']):
                await task['func']()
            else:
                task['func']()
                
            task['last_run'] = datetime.now()
            logger.info(f"Task completed: {task['func'].__name__}")
            
        except Exception as e:
            logger.error(f"Error running task {task['func'].__name__}: {str(e)}")
    
    def _scheduler_worker(self):
        """스케줄러 워커 (별도 스레드에서 실행)"""
        # 새로운 이벤트 루프 생성
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        logger.info("Background scheduler started")
        
        try:
            while self.running:
                # 실행할 작업 확인
                for task in self.tasks:
                    if self.should_run_task(task):
                        # 비동기 작업 실행
                        self.loop.run_until_complete(self.run_task(task))
                
                # 1분마다 체크
                time.sleep(60)
                
        except Exception as e:
            logger.error(f"Scheduler worker error: {str(e)}")
        finally:
            logger.info("Background scheduler stopped")
    
    def start(self):
        """스케줄러 시작"""
        if self.running:
            logger.warning("Scheduler is already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._scheduler_worker, daemon=True)
        self.thread.start()
        logger.info("Background scheduler thread started")
    
    def stop(self):
        """스케줄러 중지"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        logger.info("Background scheduler stopped")
    
    def get_status(self) -> dict:
        """스케줄러 상태 조회"""
        return {
            "running": self.running,
            "task_count": len(self.tasks),
            "tasks": [
                {
                    "name": task['func'].__name__,
                    "type": task['type'],
                    "schedule": (
                        f"Every {task['interval_minutes']} minutes" if task['type'] == 'interval'
                        else f"{'일' if task['type'] == 'daily' else ['월','화','수','목','금','토','일'][task['day_of_week']]} {task['hour']:02d}:{task['minute']:02d}"
                    ),
                    "last_run": task['last_run'].isoformat() if task['last_run'] else None
                }
                for task in self.tasks
            ]
        }


# 전역 스케줄러 인스턴스
scheduler = BackgroundScheduler()