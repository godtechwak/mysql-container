import threading
import time
import mysql.connector
from flask import Flask, request, jsonify
from conf_common.config import MYSQL_USER, MYSQL_PASSWORD, MASTER_CANDIDATES, REPLICA_CANDIDATES, HEALTHCHECK_INTERVAL, FAILOVER_TIMEOUT

app = Flask(__name__)

# 상태 관리
state = {
    "master": MASTER_CANDIDATES[0],
    "replicas": REPLICA_CANDIDATES[:],
    "last_master_ok": time.time(),
    "rr_index": 0
}

# mysql 인스턴스로 접속 가능한지 체크
def is_mysql_alive(host):
    try:
        conn = mysql.connector.connect(
            host=host, user=MYSQL_USER, password=MYSQL_PASSWORD, connection_timeout=2
        )
        conn.close()
        return True
    except Exception:
        return False

# 레플리카를 마스터로 승격
def promote_to_master(slave_host):
    # 레플리카를 마스터로 승격하는 쿼리 실행
    print(f"[Failover] {slave_host}를 새 마스터로 승격")
    try:
        conn = mysql.connector.connect(
            host=slave_host, user=MYSQL_USER, password=MYSQL_PASSWORD
        )
        cur = conn.cursor()
        cur.execute("STOP SLAVE;")
        cur.execute("RESET SLAVE ALL;")
        cur.execute("RESET MASTER;")
        cur.execute("SET GLOBAL read_only=OFF;")
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[Failover] 승격 실패: {e}")

# 새로운 마스터로 복제 연결
def reconfigure_slaves(new_master, slaves):
    for slave in slaves:
        if slave == new_master:
            continue
        print(f"[Failover] {slave}를 {new_master}에 붙이도록 재설정")
        try:
            conn = mysql.connector.connect(
                host=slave, user=MYSQL_USER, password=MYSQL_PASSWORD
            )
            cur = conn.cursor()
            cur.execute("STOP SLAVE;")
            cur.execute(f"""
                CHANGE MASTER TO MASTER_HOST='{new_master}', MASTER_USER='{MYSQL_USER}', MASTER_PASSWORD='{MYSQL_PASSWORD}', MASTER_AUTO_POSITION=1;
            """)
            cur.execute("START SLAVE;")
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"[Failover] 레플라키 재설정 실패: {e}")

def ensure_all_replicas_follow_master():
    """
    현재 마스터가 아닌 노드가 살아있고, 복제 구성이 안 되어 있으면
    자동으로 현재 마스터에 붙이도록 재설정한다.
    """
    master = state["master"]
    for node in MASTER_CANDIDATES:
        if node == master:
            continue
        if is_mysql_alive(node):
            try:
                conn = mysql.connector.connect(
                    host=node, user=MYSQL_USER, password=MYSQL_PASSWORD
                )
                cur = conn.cursor(dictionary=True)
                cur.execute("SHOW SLAVE STATUS")
                slave_status = cur.fetchone()

                # Slave_IO_Running, Slave_SQL_Running, Master_Host 등 체크
                needs_rejoin = (
                    not slave_status or
                    slave_status.get("Master_Host") != master or
                    slave_status.get("Slave_IO_Running") != "Yes" or
                    slave_status.get("Slave_SQL_Running") != "Yes"
                )
                if needs_rejoin:
                    print(f"[Rejoin] {node}를 {master}에 레플리카로 재편입")
                    cur.execute("STOP SLAVE;")
                    cur.execute(f"""
                        CHANGE MASTER TO MASTER_HOST='{master}', MASTER_USER='{MYSQL_USER}', MASTER_PASSWORD='{MYSQL_PASSWORD}', MASTER_AUTO_POSITION=1;
                    """)
                    cur.execute("START SLAVE;")
                    conn.commit()
                cur.close()
                conn.close()
            except Exception as e:
                print(f"[Rejoin] {node} 레플리카 재편입 실패: {e}")

def check_and_fix_gtid_error(slave_host):
    try:
        conn = mysql.connector.connect(
            host=slave_host, user=MYSQL_USER, password=MYSQL_PASSWORD
        )
        cur = conn.cursor(dictionary=True)
        cur.execute("SHOW SLAVE STATUS")
        status = cur.fetchone()
        if status:
            last_io_error = status.get("Last_IO_Error", "")
            if "Replica has more GTIDs than the source has" in last_io_error:
                print(f"[GTID ERROR] {slave_host}: {last_io_error}")
                print(f"[GTID AUTO-FIX] {slave_host}: RESET SLAVE ALL, RESET MASTER, START SLAVE")
                cur2 = conn.cursor()
                cur2.execute("STOP SLAVE;")
                cur2.execute("RESET SLAVE ALL;")
                cur2.execute("RESET MASTER;")
                cur2.execute("START SLAVE;")
                conn.commit()
                cur2.close()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[GTID CHECK ERROR] {slave_host}: {e}")

def healthcheck_loop():
    while True:
        master = state["master"]

        # master 서버로 접속 가능한지 확인
        if is_mysql_alive(master):
            state["last_master_ok"] = time.time()
        else:
            # 현재 시간과 마지막으로 master 서버에서 응답받은 시간의 차이가 FAILOVER_TIMEOUT을 초과할 경우 장애 조치 수행
            if time.time() - state["last_master_ok"] > FAILOVER_TIMEOUT:
                print(f"[Failover] 마스터({master}) 장애 감지!")
                
                '''
                승격할 레플리카 선택
                반복문상의 마지막 레플리카가 응답하는 경우 이전 반복문에서 응답하지 못하는 모든 레플리카를 확인해야하므로, 불필요한 시간이 낭비된다.
                추후 브로드캐스트 하여 가장 빠르게 응답을 전송하는 레플리카를 승격 대상으로 선정해야 한다.
                '''
                for candidate in state["replicas"]:
                    if is_mysql_alive(candidate):
                        # 레플리카를 마스터로 승격
                        promote_to_master(candidate)
                        new_master = candidate

                        # 새로운 마스터로 복제 연결
                        reconfigure_slaves(new_master, state["replicas"])
                        state["master"] = new_master

                        # 새 레플리카 목록 갱신
                        state["replicas"] = [h for h in MASTER_CANDIDATES if h != new_master]
                        state["last_master_ok"] = time.time()
                        break
        
        # 모든 노드가 현재 마스터를 따라가도록 한다. (보장 의도)
        ensure_all_replicas_follow_master()

        # 각 레플리카의 GTID 오류 자동 복구
        for slave in state["replicas"]:
            check_and_fix_gtid_error(slave)
        time.sleep(HEALTHCHECK_INTERVAL)

# Read 쿼리 분산 처리
@app.route("/read", methods=["POST"])
def read_query():
    # 레플리카가 존재하지 않는 경우
    if not state["replicas"]:
        return jsonify({"error": "No available replicas"}), 503
    query = request.json.get("query")
    
    # 라운드로빈 방식으로 레플리카 선택
    idx = state["rr_index"] % len(state["replicas"])
    host = state["replicas"][idx]
    state["rr_index"] += 1

    try:
        conn = mysql.connector.connect(
            host=host, user=MYSQL_USER, password=MYSQL_PASSWORD
        )
        cur = conn.cursor()
        cur.execute(query)
        result = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify({"host": host, "result": result})
    except Exception as e:
        return jsonify({"error": str(e), "host": host}), 500

if __name__ == "__main__":
    t = threading.Thread(target=healthcheck_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5000) 