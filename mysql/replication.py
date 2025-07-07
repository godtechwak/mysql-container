import docker
import time
import os
import shutil
import socket
from dbuser.user_management import create_replication_user, create_monitor_user, create_orchestrator_user
from conf_common.config import NETWORK_NAME, MYSQL_IMAGE, MYSQL_REPL_PASSWORD, MYSQL_REPL_USER, MYSQL_ROOT_PASSWORD
from util.exec_mysql import exec_mysql

# Docker API
client = docker.from_env()

# 기본 3개 인스턴스 구성
INSTANCE_COUNT = int(os.environ.get("INSTANCE_COUNT", 3)) 
 
# 기본 3307 부터 포트 포워딩 시작
START_PORT = int(os.environ.get("START_PORT", 3307))

# 마스터 인스턴스는 00번 부터 시작
MASTER_NAME = f"mysql-00"

# INSTANCE_COUNT 만큼 순회하면서 레플리카와 포트를 순차적으로 구성한다.
SLAVES = [(f"mysql-{i:02d}", i+1) for i in range(1, INSTANCE_COUNT)]
PORT_MAP = {f"mysql-{i:02d}": START_PORT + i for i in range(INSTANCE_COUNT)}

# 컨테이너 통신
def create_network():
    try:
        client.networks.get(NETWORK_NAME)
        print(f"네트워크 '{NETWORK_NAME}' 이미 존재함.")
    except docker.errors.NotFound:
        client.networks.create(NETWORK_NAME, driver="bridge")
        print(f"네트워크 '{NETWORK_NAME}' 생성 완료.")

# 생성하려는 컨테이너가 존재하는 경우 제거
def remove_if_exists(name):
    try:
        container = client.containers.get(name)
        print(f"기존 컨테이너 '{name}' 제거 중...")
        container.remove(force=True)
    except docker.errors.NotFound:
        pass

# 복제 토폴로지에 구성된 인스턴스들의 my.cnf 파일을 생성한다.
def generate_my_cnf(server_id, replica_count=None):
    # If replica_count is not provided, default to SLAVES length
    if replica_count is None:
        replica_count = len(SLAVES)
    # Set majority quorum
    wait_for_slave_count = max(1, (replica_count // 2) + 1)
    return f"""
[mysqld]
server-id={server_id}
gtid_mode=ON
enforce_gtid_consistency=ON
log_bin=mysql-bin
log_slave_updates=ON
binlog_format=ROW

plugin-load-add=semisync_master.so
plugin-load-add=semisync_slave.so
loose-rpl_semi_sync_master_enabled=1
loose-rpl_semi_sync_slave_enabled=1
loose-rpl_semi_sync_master_timeout=1000
loose-rpl_semi_sync_master_wait_for_slave_count={wait_for_slave_count}
"""

# 컨테이너 상태가 running으로 변경될 때까지 60초동안 반복 시도
def wait_for_mysql_ready(container, timeout=60):
    print(f"'{container.name}' MySQL 서버 준비 대기 중...")
    for _ in range(timeout):
        container.reload()
        if container.status != "running":
            raise RuntimeError(f"컨테이너 '{container.name}' 종료됨. 상태: {container.status}")
        try:
            exit_code, _ = container.exec_run(
                f"mysqladmin ping -uroot -p{MYSQL_ROOT_PASSWORD}",
                stdout=True, stderr=False
            )
            if exit_code == 0:
                print(f"'{container.name}' MySQL 준비 완료.\n")
                return True
        except docker.errors.APIError:
            pass
        time.sleep(1)
    raise TimeoutError(f"'{container.name}' MySQL 서버가 {timeout}초 내에 준비되지 않았습니다.")

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0

# 컨테이너 셋업
def start_container(name, server_id, volume_path):
    # 컨테이너가 존재하는 경우 삭제
    remove_if_exists(name)

    # 포트맵에서 컨테이너명으로 포트를 받아온다.
    port = PORT_MAP.get(name)

    if os.path.exists(volume_path):
        shutil.rmtree(volume_path)
    os.makedirs(volume_path, exist_ok=True)

    # 컨테이너의 my.cnf 설정
    conf_host_path = os.path.abspath(f"{volume_path}/my.cnf")
    with open(conf_host_path, "w") as f:
        f.write(generate_my_cnf(server_id, len(SLAVES)))

    # 컨테이너의 데이터 디렉터리 설정
    mysql_data_path = f"/tmp/{name}_data"
    if os.path.exists(mysql_data_path):
        shutil.rmtree(mysql_data_path)
    os.makedirs(mysql_data_path, exist_ok=True)

    ports = { "3306/tcp": port }

    # 컨테이너 <-> 호스트 바인딩 작업 및 컨테이너 실행
    print(f"컨테이너 '{name}' 시작 중...")
    container = client.containers.run(
        MYSQL_IMAGE,
        name=name,
        detach=True,
        environment={"MYSQL_ROOT_PASSWORD": MYSQL_ROOT_PASSWORD},
        volumes={
            conf_host_path: {"bind": "/etc/mysql/conf.d/my.cnf", "mode": "ro"},
            os.path.abspath(mysql_data_path): {"bind": "/var/lib/mysql", "mode": "rw"},
        },
        ports=ports,
        network=NETWORK_NAME,
    )
    return container

# 마스터 컨테이너 셋업
def setup_master_container():
    container = start_container(MASTER_NAME, 1, "./conf_mysql-00")
    wait_for_mysql_ready(container)
    return container

# 레플리카 컨테이너 설정
def setup_slave_containers():
    containers = []
    for name, sid in SLAVES:
        container = start_container(name, sid, f"./conf_{name}")
        wait_for_mysql_ready(container)
        containers.append(container)
    return containers

# 복제 설정
def configure_slaves(slave_containers):
    for container in slave_containers:
        print(f"'{container.name}' 복제 설정 중...")
        exec_mysql(container, f"""
            CHANGE MASTER TO
              MASTER_HOST='{MASTER_NAME}',
              MASTER_PORT=3306,
              MASTER_USER='{MYSQL_REPL_USER}',
              MASTER_PASSWORD='{MYSQL_REPL_PASSWORD}',
              MASTER_AUTO_POSITION=1;
            START SLAVE;
        """)
        print(f"'{container.name}' 복제 시작됨.")
        result = exec_mysql(container, "SHOW SLAVE STATUS\\G")
        print(result.output.decode() if result.output else "!! 출력 없음")


def main():
    # 컨테이너끼리 통신하기 위한 네트워크 설정
    create_network()

    # 마스터 컨테이너 생성
    master_container = setup_master_container()

    # 레플리카 컨테이너 생성
    slave_containers = setup_slave_containers()

    # 기타 잔여 작업이 마무리될 때까지 10초 대기
    time.sleep(10)

    # 복제 계정 생성
    create_replication_user(master_container)

    # 모니터링 계정 생성
    create_monitor_user(master_container)

    # 오케스트레이터 계정 생성
    create_orchestrator_user(master_container)

    # 복제 설정
    configure_slaves(slave_containers)

    # 슬레이브에도 orchestrator 계정 생성
    for container in slave_containers:
        create_orchestrator_user(container)

if __name__ == "__main__":
    main()
