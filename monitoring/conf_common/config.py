import os

MONITOR_SERVERS = os.getenv("MONITOR_SERVERS", "mysql-00,mysql-01,mysql-02").split(",")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "monitor")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "monitorpass")
INTERVAL = 5  # 초
MAX_SECONDS = 900  # 15분
MAX_HISTORY = MAX_SECONDS // INTERVAL  # 최대 저장 개수

# GLOBAL STATUS 항목
MYSQL_STATUS_KEYS = [
    'Threads_connected', 'Slow_queries', 'Queries',
    'Com_select', 'Com_delete', 'Com_update', 'Com_insert',
    'Innodb_rows_read', 'Innodb_rows_deleted', 'Innodb_rows_updated', 'Innodb_rows_inserted'
]