import subprocess
import re
import logging
import pandas as pd
from K_connection import connect_to_db, record_exists_in_db, update_record_in_db,insert_record_into_db,cve_exists_in_cvssv2,fetch_cve_details
from datetime import datetime
def pod_count(deployment_name, namespace):
    try:
        command = ["kubectl", "get", "deployment", deployment_name, "-n", namespace, "-o=jsonpath='{.spec.replicas}'"]
        output = subprocess.check_output(command).decode('utf-8').strip("'")
        return int(output)
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to get pod count for deployment '{deployment_name}': {e}")
        return 0
def list_pods(namespace,deployment):
    command = f"kubectl get pods -n {namespace} -l app={deployment} -o jsonpath='{{.items[*].metadata.name}}'"
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        pod_names = result.stdout.strip().split()
        return pod_names
    else:
        logging.error("Failed to get pods. Error: %s", result.stderr)
    return []

def risk_analysis(service_name,df,namespace):
    severity_order = {'LOW': 1, 'MEDIUM': 2, 'HIGH': 3, 'CRITICAL': 4}
    df = df.drop_duplicates()
    
    unique_cves = df['CVE Number'].unique().tolist()
    conn = connect_to_db()
    cve_details = fetch_cve_details(conn, unique_cves)
    conn.close()
    
    cve_df = pd.DataFrame(cve_details, columns=['cve', 'baseScore', 'severity', 'mitigation'])
    
    merged_df = df.merge(cve_df, left_on='CVE Number', right_on='cve', how='left').drop(columns=['cve'])
    if merged_df.empty:
        return None
    
    merged_df['severity_num'] = merged_df['severity'].map(severity_order)
    merged_df['baseScore'] = merged_df['baseScore'].astype(float)
    
    totalRisk = int(merged_df['severity_num'].sum())*pod_count(service_name, namespace)
    
    top_cve_row = merged_df.loc[merged_df['baseScore'].idxmax()]
    topCVE = top_cve_row['CVE Number']
    mitigation = top_cve_row['mitigation']
    
    return {
        'serviceName': service_name,
        'totalRisk': totalRisk,
        'topCVE': topCVE,
        'mitigation': mitigation
    }

def planning(results_dict):
    df = pd.DataFrame.from_dict(results_dict, orient='index')
    df = df.sort_values(by='cpu_usage', ascending=False)
    
    if len(df) == 1:
        df['recommended'] = 1
    else:
        split_index = len(df) // 2
        df['recommended'] = 0
        df.loc[df.index[:split_index], 'recommended'] = 1  
    
    updated_results_dict = df.to_dict(orient='index')
    return updated_results_dict


def read(service,namespace):
    conn = connect_to_db()
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
        results = risk_analysis(service,df,namespace)
        return results

def scan(service_name, namespace):
    logging.info(f'Scanning {service_name}')
    #pod_names = list_pods(namespace,service_name)
    conn = connect_to_db()
    try:
        #for pod_name in pod_names:
        trivy_command = f"trivy k8s --format json --namespace {namespace} deployment {service_name}"
        trivy_result = subprocess.run(trivy_command, shell=True, capture_output=True, text=True)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if trivy_result.returncode == 0:
            cve_numbers = re.findall(r'CVE-\d{4}-\d+', trivy_result.stdout)
                    
            for cve_number in cve_numbers:
                if not cve_exists_in_cvssv2(conn, cve_number):
                    continue
                status_in_db = record_exists_in_db(conn, cve_number, service_name)
                        
                if status_in_db == 'Solved':
                    continue
                        
                if status_in_db:
                    update_record_in_db(conn, cve_number, service_name, status_in_db, timestamp)
                else:
                    insert_record_into_db(conn, timestamp, cve_number, service_name, 'Unsolved')
            else:
                logging.error(f"Failed to scan pod {service_name}. Error: {trivy_result.stderr}")
            conn.commit()  # Commit the transaction
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        conn.rollback()  # Rollback the transaction in case of error
    finally:
        conn.close()  # Close the connection


