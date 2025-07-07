import requests
import time

# 오케스트레이터가 Read Proxy 역할을 하며, RESTFUL API 형태로 쿼리를 실행한다.
query="SELECT 1"

while True:
    resp = requests.post("http://localhost:5050/read", json={"query": f"{query}"})
    print(resp.json())
    time.sleep(1)
