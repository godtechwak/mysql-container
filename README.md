# Description
- Replication: 1 대 N 구조의 복제 구성
- Orchestrator: 자동 장애 조치 및 읽기 분산 라우팅
- Monitoring: 5초마다 Real-Time으로 메트릭 수집

# How to Use
1. mysql 디렉터리에서 build.sh 실행
- 마스터와 레플리카 컨테이너 생성
- 복제, 모니터, 오케스트레이터 계정 생성
- 복제 연결
- 오케스트레이터 컨테이너 생성
- mysql -u root -h 127.0.0.1 -P 3307 -p 접속 (레플리카는 3308부터)

2. monitoring 디렉터리에서 build.sh 실행
- 모니터링 컨테이너 생성
- http://127.0.0.1:6060 접속하여 모니터링

3. mysql/query 디렉터리에서 read_query.py 실행
- "http://localhost:5050/read" 엔드포인트로 서비스 쿼리 시, 오케스트레이터가 레플리카로 부하 분산(라운드 로빈 방식)