from conf_common.config import MYSQL_ROOT_PASSWORD

# SQL 실행 도우미 함수
def exec_mysql(container, sql):
    cmd = f'mysql -uroot -p{MYSQL_ROOT_PASSWORD} -e "{sql}"'
    result = container.exec_run(cmd)
    if result.exit_code != 0:
        print(f"SQL 실행 실패: {sql.strip()}")
        print(result.output.decode(errors='ignore'))
    else:
        print(f"SQL 실행 완료:\n{sql.strip()}")
    return result