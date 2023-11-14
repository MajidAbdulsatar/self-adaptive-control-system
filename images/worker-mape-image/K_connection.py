import psycopg2
import pandas as pd
import traceback
import logging
from cpu_ut import deployment_cpu_percentage, pod_count
def connect_to_db():
    conn = psycopg2.connect(
        dbname="mydatabase",
        user="user",
        password="password",
        host="postgres-service",
        port="5432"
    )
    return conn

#The following functions for cve scanning ONLY!
def record_exists_in_db(conn, cve, service):
    with conn.cursor() as cursor:
        cursor.execute("SELECT status FROM worker_cve_scan WHERE cve=%s AND service=%s", (cve, service))
        result = cursor.fetchone()
        return result[0] if result else None

def update_record_in_db(conn, cve, service, status, timestamp):
    with conn.cursor() as cursor:
        cursor.execute("UPDATE worker_cve_scan SET dateandtime=%s, status=%s WHERE cve=%s AND service=%s", (timestamp, status, cve, service))
        conn.commit()

def insert_record_into_db(conn, timestamp, cve, service, status):
    with conn.cursor() as cursor:
        cursor.execute("INSERT INTO worker_cve_scan (dateandtime, cve, service, status) VALUES (%s, %s, %s, %s)", (timestamp, cve, service, status))
        conn.commit()

def cve_exists_in_cvssv2(conn, cve):
    with conn.cursor() as cursor:
        cursor.execute('SELECT 1 FROM "CVSSV2" WHERE cve=%s', (cve,))
        return cursor.fetchone() is not None
    
def fetch_cve_details(conn, cves):
    query = 'SELECT "cve", "baseScore", "severity", "mitigation" FROM "CVSSV2" WHERE "cve" = ANY(%s)'
    with conn.cursor() as cursor:
        cursor.execute(query, (cves,))
        return cursor.fetchall()
    

    

# the following is the action section 
def fetch_service_status(service,conn):
    with conn.cursor() as cursor:
        query = """
            SELECT dateandtime, cve, service, status 
            FROM worker_cve_scan 
            WHERE service = %s AND status = 'Unsolved'
        """
        cursor.execute(query, (service,))
        data =  cursor.fetchall()
        columns = ['Timestamp', 'CVE Number', 'Service', 'Status']
        df = pd.DataFrame(data, columns=columns)
        return df

def calculate_total_risk(service):
    conn = connect_to_db()
    severity_order = {'LOW': 1, 'MEDIUM': 2, 'HIGH': 3, 'CRITICAL': 4}
    # Fetch CVE details from CVSSV2
    df = fetch_service_status(service, conn)
    cve_list = df['CVE Number'].unique().tolist()
    cve_details = fetch_cve_details(conn, cve_list)
    cve_df = pd.DataFrame(cve_details, columns=['cve', 'baseScore', 'severity', 'mitigation'])
    merged_df = df.merge(cve_df, left_on='CVE Number', right_on='cve', how='left').drop(columns=['cve'])
    if merged_df.empty:
        return 0
    merged_df['severity_num'] = merged_df['severity'].map(severity_order)
    totalRisk = int(merged_df['severity_num'].sum())
    return totalRisk

def update_worker_cve_scan(cursor, top_cve, service):
    query = "UPDATE worker_cve_scan SET status='Solved' WHERE cve=%s AND service=%s"
    cursor.execute(query, (top_cve, service))

def insert_into_actions_table(cursor, service, data, worker_id, worker_loop):
    query = """
        INSERT INTO actions_table (
            timestamp, service_name,
            topCVE, mitigation,
            recommended, decision,
            worker_id, actioned_by, worker_loop
        ) VALUES (DEFAULT, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    cursor.execute(query, (
        service,
        data['topCVE'], data['mitigation'],
        data['recommended'], data.get('decision', 0),
        worker_id, 'Main', worker_loop
    ))

def insert_into_stat_table(cursor, service, data, current_replicas):
    query = """
        INSERT INTO stat_table (timestamp,service, totalRisk, cpuUsage, numReplicas)
        VALUES (DEFAULT,%s, %s, %s, %s)
    """
    cursor.execute(query, (service, data['totalRisk'], data['cpu_usage'], current_replicas+1))

def action(input_dict, worker_id, worker_loop, namespace):
    conn = connect_to_db()
    try:
        with conn.cursor() as cursor:
            for service, data in input_dict.items():
                if data['decision'] == 1:
                    update_worker_cve_scan(cursor, data['topCVE'], service)
                    insert_into_actions_table(cursor, service, data, worker_id, worker_loop)
                    #current_replicas = fetch_cpu_stat(service)
                    # if data['cpu_usage'] > 50 and current_replicas < 5:
                    #     insert_into_stat_table(cursor, service, data, current_replicas)
            conn.commit()
    except Exception as e:
        print(f"An error occurred: {e}")
        print(traceback.format_exc())
        conn.rollback()
    finally:
        conn.close()


def fallbackAction(input_dict, worker_id, worker_loop, namespace):
    conn = connect_to_db()
    try:
        with conn.cursor() as cursor:
            for service, data in input_dict.items():
                if data['recommended'] == 1:
                    update_worker_cve_scan(cursor, data['topCVE'], service)
                    insert_into_actions_table(cursor, service, data, worker_id, worker_loop)
                    #current_replicas = fetch_cpu_stat(service)
                    # if data['cpu_usage'] > 50 and current_replicas < 5:
                    #     insert_into_stat_table(cursor, service, data, current_replicas)
            conn.commit()
    except Exception as e:
        print(f"An error occurred: {e}")
        print(traceback.format_exc())
        conn.rollback()
    finally:
        conn.close()

def stat(service,namespace):
    cpuUsage = deployment_cpu_percentage(namespace,service)
    numReplicas = pod_count(service,namespace)
    totalRisk = calculate_total_risk(service)
    conn = connect_to_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO stat_table (
                    timestamp,service, totalRisk, cpuUsage, numReplicas
                ) VALUES (DEFAULT,%s, %s, %s, %s)
                """,
                (service, totalRisk, cpuUsage, numReplicas)
            )
        conn.commit()
    except Exception as e:
        print(f"An error occurred: {e}")
        print(traceback.format_exc())
        conn.rollback()
    finally:
        conn.close()

