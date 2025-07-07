#!/bin/sh 

set -e

read -p "MySQL 인스턴스 개수? (기본: 3): " INSTANCE_COUNT
INSTANCE_COUNT=${INSTANCE_COUNT:-3}
read -s -p "MySQL monitor(모니터링) 계정 비밀번호? (기본: monitorpass): " MYSQL_MONITOR_PASSWORD; echo
MYSQL_MONITOR_PASSWORD=${MYSQL_MONITOR_PASSWORD:-monitorpass}

MONITOR_SERVERS=""
for i in $(seq 0 $((INSTANCE_COUNT-1))); do
  if [ $i -ne 0 ]; then MONITOR_SERVERS+=","; fi
  MONITOR_SERVERS+="mysql-$(printf "%02d" $i)"
done

MYSQL_PORT=3306

# metrics-dashboard 도커 빌드
docker build -f Dockerfile.metrics -t metrics-dashboard .

# 기존에 생성되어 있는 컨테이너 삭제
docker rm -f metrics-dashboard 2>/dev/null || true

# 컨테이너 실행
docker run -d --name metrics-dashboard --network mysql-net \
  -e MONITOR_SERVERS="$MONITOR_SERVERS" \
  -e MYSQL_PORT=$MYSQL_PORT \
  -e MYSQL_USER=monitor \
  -e MYSQL_PASSWORD="$MYSQL_MONITOR_PASSWORD" \
  -p 6060:6000 \
  metrics-dashboard