"""
Celery 配置與應用程序初始化
"""
import os
from celery import Celery
from .core.config import settings

# 設置默認的 Celery 配置模塊
os.environ.setdefault('CELERY_CONFIG_MODULE', 'src.celeryconfig')

# 創建 Celery 應用程序
app = Celery('contract_deid')

# 從配置模塊加載配置
app.config_from_envvar('CELERY_CONFIG_MODULE')

# 自動發現任務
app.autodiscover_tasks(['src.tasks'])

# 配置 Celery 應用程序
app.conf.update(
    # Broker 設置
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,
    
    # 任務序列化設置
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # 時區設置
    timezone='Asia/Taipei',
    enable_utc=True,
    
    # 任務設置
    task_track_started=True,
    task_time_limit=3600,  # 1 小時超時
    task_soft_time_limit=3300,  # 55 分鐘軟超時
    
    # 結果設置
    result_expires=60 * 60 * 24 * 3,  # 3 天過期
    
    # 工作進程設置
    worker_pool="solo",          # macOS 上 prefork fork 後載入 PyTorch/spaCy 會 SIGSEGV,強制 solo
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    
    # 路由設置
    task_routes={
        'src.tasks.process_document': {'queue': 'doc_processing'},
    },
    
    # 監控設置
    worker_send_task_events=True,
    task_send_sent_event=True,
)

if __name__ == '__main__':
    app.start()
