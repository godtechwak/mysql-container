#!/bin/sh 

set -e

read -p "MySQL 인스턴스 개수? (기본: 3): " INSTANCE_COUNT
INSTANCE_COUNT=${INSTANCE_COUNT:-3}
read -p "시작 포트? (기본: 3307): " START_PORT
START_PORT=${START_PORT:-3307}
read -s -p "MySQL root 비밀번호? (기본: rootpass): " MYSQL_ROOT_PASSWORD; echo
MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD:-rootpass}
read -s -p "MySQL repl(복제) 계정 비밀번호? (기본: replpass): " MYSQL_REPL_PASSWORD; echo
MYSQL_REPL_PASSWORD=${MYSQL_REPL_PASSWORD:-replpass}
read -s -p "MySQL monitor(모니터링) 계정 비밀번호? (기본: monitorpass): " MYSQL_MONITOR_PASSWORD; echo
MYSQL_MONITOR_PASSWORD=${MYSQL_MONITOR_PASSWORD:-monitorpass}
read -s -p "MySQL orchestrator(오케스트레이터) 계정 비밀번호? (기본: orchestratorpass): " MYSQL_ORCH_PASSWORD; echo
MYSQL_ORCH_PASSWORD=${MYSQL_ORCH_PASSWORD:-orchestratorpass}

# 포트를 점유하고 있는 mysql-XX 컨테이너를 삭제한다.
for i in $(seq 0 $((INSTANCE_COUNT-1))); do
  PORT=$((START_PORT + i))
  # 포트 점유한 컨테이너 검색
  CID=$(docker ps -a --filter "publish=$PORT" --format "{{.ID}}")
  if [ -n "$CID" ]; then
    echo "포트 ($PORT)를 점유한 컨테이너($CID)를 삭제합니다."
    docker rm -f $CID
  fi
done

export INSTANCE_COUNT
export START_PORT
export MYSQL_ROOT_PASSWORD
export MYSQL_REPL_PASSWORD
export MYSQL_MONITOR_PASSWORD
export MYSQL_ORCH_PASSWORD

# 1 (Replication 구성)
python3 replication.py

MASTER_CANDIDATES=$(seq -f "mysql-%02g" 0 $((INSTANCE_COUNT-1)) | paste -sd "," -)
REPLICA_CANDIDATES=$(seq 1 $((INSTANCE_COUNT-1)) | xargs -I{} printf "mysql-%02d," {} | sed 's/,$//')

# 2 (오케스트레이터 도커 빌드)
docker build -f Dockerfile.orchestrator -t mysql-orchestrator .

# 3 (컨테이너가 이미 존재하면 삭제)
docker rm -f mysql-orchestrator 2>/dev/null || true

# 4 (컨테이너 실행)
docker run -d --name mysql-orchestrator --network mysql-net \
  -e MYSQL_USER=orchestrator \
  -e MYSQL_PASSWORD="$MYSQL_ORCH_PASSWORD" \
  -e MASTER_CANDIDATES="$MASTER_CANDIDATES" \
  -e REPLICA_CANDIDATES="$REPLICA_CANDIDATES" \
  -e HEALTHCHECK_INTERVAL=2 \
  -e FAILOVER_TIMEOUT=5 \
  -p 5050:5000 \
  mysql-orchestrator
