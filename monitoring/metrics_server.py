import time
import threading
import psutil
import mysql.connector
from flask import Flask, jsonify, request, send_from_directory
import os
from conf_common.config import MONITOR_SERVERS, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, INTERVAL, MAX_HISTORY, MYSQL_STATUS_KEYS

app = Flask(__name__)

# 서버별 메트릭 히스토리
metrics_history = {server: [] for server in MONITOR_SERVERS}

# 주기적으로 각 MySQL 서버의 메트릭을 수집하는 함수
def collect_metrics():
    while True:
        for server in MONITOR_SERVERS:
            try:
                conn = mysql.connector.connect(
                    host=server, port=MYSQL_PORT,
                    user=MYSQL_USER, password=MYSQL_PASSWORD
                )
                keys_str = "','".join(MYSQL_STATUS_KEYS)
                cur = conn.cursor(dictionary=True)

                # 1. 기타 메트릭
                cur.execute(f"SHOW GLOBAL STATUS WHERE Variable_name IN ('{keys_str}')")
                status = {row['Variable_name'].lower(): int(row['Value']) for row in cur.fetchall()}

                # 2. 언두 로그(Innodb_history_list_length)
                try:
                    cur.execute("SELECT count FROM information_schema.innodb_metrics WHERE name='trx_rseg_history_len' LIMIT 1")
                    row = cur.fetchone()
                    if row and 'count' in row:
                        status['innodb_history_list_length'] = int(row['count'])
                    else:
                        status['innodb_history_list_length'] = 0
                except Exception:
                    status['innodb_history_list_length'] = 0
                
                # 3. 복제 지연(Seconds_Behind_Master)
                try:
                    cur.execute("SHOW SLAVE STATUS")
                    slave_status = cur.fetchone()
                    if slave_status and 'Seconds_Behind_Master' in slave_status and slave_status['Seconds_Behind_Master'] is not None:
                        status['replication_lag'] = int(slave_status['Seconds_Behind_Master'])
                    else:
                        status['replication_lag'] = None
                except Exception:
                    status['replication_lag'] = None
                cur.close()
                conn.close()
            except Exception as e:
                status = {"error": str(e)}
            sys_status = {
                "cpu_percent": psutil.cpu_percent(),
                "mem_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage('/').percent,
            }
            metrics = {
                "timestamp": int(time.time()),
                "mysql": status,
                "system": sys_status
            }
            metrics_history[server].append(metrics)
            
            # 15분(900초) 이상이면 오래된 데이터 삭제
            if len(metrics_history[server]) > MAX_HISTORY:
                metrics_history[server].pop(0)
        time.sleep(INTERVAL)

@app.route("/metrics")
def get_metrics():
    server = request.args.get("server", MONITOR_SERVERS[0])
    if server not in metrics_history:
        return jsonify({"error": "Unknown server"}), 400
    return jsonify(metrics_history[server])

@app.route("/")
def serve_index():
    return send_from_directory("static", "index.html")

@app.route("/static/<path:path>")
def serve_static(path):
    return send_from_directory("static", path)

@app.route("/servers")
def get_servers():
    return jsonify(MONITOR_SERVERS)

if __name__ == "__main__":
    t = threading.Thread(target=collect_metrics, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=6000) 