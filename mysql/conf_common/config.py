import os

# 공통 설정
MYSQL_IMAGE = "mysql:8.0"
NETWORK_NAME = "mysql-net"
MYSQL_ROOT_PASSWORD = os.environ.get("MYSQL_ROOT_PASSWORD", "rootpass")
MYSQL_REPL_USER = "repl"
MYSQL_REPL_PASSWORD = os.environ.get("MYSQL_REPL_PASSWORD", "replpass")
MYSQL_MONITOR_PASSWORD = os.environ.get("MYSQL_MONITOR_PASSWORD", "monitorpass")
MYSQL_ORCH_PASSWORD = os.environ.get("MYSQL_ORCH_PASSWORD", "orchestratorpass")
MYSQL_USER = os.getenv("MYSQL_USER", "orchestrator")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MASTER_CANDIDATES = os.getenv("MASTER_CANDIDATES", "mysql-00,mysql-01,mysql-02").split(",")
REPLICA_CANDIDATES = os.getenv("REPLICA_CANDIDATES", "mysql-01,mysql-02").split(",")
HEALTHCHECK_INTERVAL = int(os.getenv("HEALTHCHECK_INTERVAL", "2")) 
FAILOVER_TIMEOUT = int(os.getenv("FAILOVER_TIMEOUT", "5"))