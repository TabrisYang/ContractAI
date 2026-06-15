"""
Celery 配置文件
"""
from .core.config import settings

# Broker 設置
broker_url = settings.REDIS_URL
result_backed = settings.REDIS_URL

# 任務序列化設置
task_serializer = 'json'
result_serializer = 'json'
accept_content = ['json']

# 時區設置
timezone = 'Asia/Taipei'
enable_utc = True

# 任務設置
task_track_started = True
task_time_limit = 3600  # 1 小時超時
task_soft_time_limit = 3300  # 55 分鐘軟超時

# 結果設置
result_expires = 60 * 60 * 24 * 3  # 3 天過期

# 工作進程設置
worker_prefetch_multiplier = 1
worker_max_tasks_per_child = 100

# 路由設置
task_routes = {
    'src.tasks.process_document': {'queue': 'doc_processing'},
}

# 監控設置
worker_send_task_events = True
task_send_sent_event = True

# 日誌設置
worker_log_format = "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s"
worker_task_log_format = "[%(asctime)s: %(levelname)s/%(processName)s] [%(task_name)s(%(task_id)s)] %(message)s"
