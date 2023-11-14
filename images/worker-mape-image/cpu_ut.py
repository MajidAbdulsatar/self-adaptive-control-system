import subprocess
import logging
import psycopg2
import re
import math
import statistics
import time
import logging

def connect_to_db():
    conn = psycopg2.connect(
        dbname="mydatabase",
        user="user",
        password="password",
        host="postgres-service",
        port="5432"
    )
    return conn
def pod_count(deployment_name, namespace):
    try:
        command = ["kubectl", "get", "deployment", deployment_name, "-n", namespace, "-o=jsonpath='{.spec.replicas}'"]
        output = subprocess.check_output(command).decode('utf-8').strip("'")
        return int(output)
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to get pod count for deployment '{deployment_name}': {e}")
        return None

def deployment_cpu_percentage(namespace, deployment_name):
    command = f'kubectl top pods -n {namespace} -l app={deployment_name} --no-headers'
    output = subprocess.check_output(command.split()).decode('utf-8')
    
    cpu_values = []
    
    for line in output.splitlines():
        match = re.search(r'(\d+)m', line)
        if match:
            cpu_value = float(match.group(1))
            cpu_values.append(cpu_value)
        else:
            logging.error(f"Failed to extract CPU value. Output: {line}")
            
    avg_cpu = math.ceil(statistics.mean(cpu_values)) if cpu_values else 0
    
    cpu_request_command = f"kubectl get deployment {deployment_name} -n {namespace} -o=jsonpath='{{.spec.template.spec.containers[0].resources.requests.cpu}}'"
    cpu_request_output = subprocess.check_output(cpu_request_command.split()).decode('utf-8').strip().strip("'")
    
    try:
        cpu_request = float(cpu_request_output.rstrip('m'))
        
    except ValueError:
        cpu_request = 100
    cpu_percentage = (avg_cpu / cpu_request) * 100
    replicas = pod_count(deployment_name, namespace) #fetch_cpu_stat(deployment_name)
    cpu_percentage = cpu_percentage /replicas
    return round(cpu_percentage,2)

def upscale_deployment(deployment_name, namespace, current_pod_count, cpu_utilization):
    # Constants
    THRESHOLD_PER_POD = 50
    MAX_PODS = 3
    current_pod_count = pod_count(deployment_name,namespace)
    cpu_utilization = cpu_utilization * current_pod_count
    if cpu_utilization>=THRESHOLD_PER_POD:
        # Calculate desired replicas based on CPU utilization
        desired_replicas = math.ceil(cpu_utilization / THRESHOLD_PER_POD)

        # Ensure the replicas are within the range [1, MAX_PODS]
        desired_replicas = max(1, min(desired_replicas, MAX_PODS))

        if desired_replicas == current_pod_count:
            logging.info(f"No need to scale '{deployment_name}'. Current and desired replicas are the same: {current_pod_count}.")
            return

        # Scale the deployment
        try:
            command = ["kubectl", "scale", "deployment", deployment_name, f"--replicas={desired_replicas}", f"-n{namespace}"]
            subprocess.run(command)
            
            # Wait for scaling to take effect 
            time.sleep(5)

            logging.info(f"Scaled deployment '{deployment_name}' to {desired_replicas} replicas based on CPU utilization.")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to scale deployment '{deployment_name}': {e}")

