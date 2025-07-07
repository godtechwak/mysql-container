import os
from util.exec_mysql import exec_mysql
from conf_common.config import MYSQL_REPL_USER, MYSQL_REPL_PASSWORD, MYSQL_MONITOR_PASSWORD, MYSQL_ORCH_PASSWORD

def create_replication_user(container):
    print(f"Master에 복제 계정 생성 중...")
    exec_mysql(container, f"""
        DROP USER IF EXISTS '{MYSQL_REPL_USER}'@'%';
        CREATE USER '{MYSQL_REPL_USER}'@'%' IDENTIFIED WITH mysql_native_password BY '{MYSQL_REPL_PASSWORD}' PASSWORD EXPIRE NEVER ACCOUNT UNLOCK;
        GRANT REPLICATION SLAVE ON *.* TO '{MYSQL_REPL_USER}'@'%';
        FLUSH PRIVILEGES;
    """)

def create_monitor_user(container):
    print(f"Master에 모니터링 계정 생성 중...")
    exec_mysql(container, f'''
        DROP USER IF EXISTS 'monitor'@'%';
        CREATE USER 'monitor'@'%' IDENTIFIED WITH 'mysql_native_password' BY '{MYSQL_MONITOR_PASSWORD}' PASSWORD EXPIRE NEVER ACCOUNT UNLOCK;
        GRANT SELECT, PROCESS, REPLICATION CLIENT, RELOAD ON *.* TO 'monitor'@'%';
        GRANT SELECT ON performance_schema.* TO 'monitor'@'%';
        FLUSH PRIVILEGES;
    ''')

def create_orchestrator_user(container):
    print(f"{container.name}에 orchestrator 계정 생성 중...")
    exec_mysql(container, f'''
        DROP USER IF EXISTS 'orchestrator'@'%';
        CREATE USER 'orchestrator'@'%' IDENTIFIED WITH 'mysql_native_password' BY '{MYSQL_ORCH_PASSWORD}' PASSWORD EXPIRE NEVER ACCOUNT UNLOCK;
        GRANT ALL PRIVILEGES ON *.* TO 'orchestrator'@'%' WITH GRANT OPTION;
        FLUSH PRIVILEGES;
    ''') 