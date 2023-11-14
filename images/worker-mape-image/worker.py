from flask import Flask, jsonify
import logging 
import time
import requests
import subprocess
import pandas as pd
from uuid import uuid4
from scanner import scan, planning,read
from cpu_ut import deployment_cpu_percentage, upscale_deployment
from K_connection import action,stat,fallbackAction
from main_communication import register_worker, send_results, polling_for_decisions
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
class CustomFormatter(logging.Formatter):

    grey = "\x1b[38;21m"
    yellow = "\x1b[33;21m"
    red = "\x1b[31;21m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(CustomFormatter())
logger.addHandler(ch)

app = Flask(__name__)

MAIN_MAPE_URL = 'http://main-mape-service.development.svc.cluster.local:80'
def print_table(data):
    data_list = list(data.values())
    df = pd.DataFrame(data_list)
    df = df.sort_values(by='cpu_usage',ascending=False)
    table_string = df.to_string(index=False)
    logging.info('\n' + table_string)

def worker_mape():
    worker_loop_counter = 0
    start_time = time.time()
    while True:
        time_elapsed = time.time() - start_time
        if time_elapsed >= 900:
            #after 15 min break
            break
        results_dict = {}
        for service in services:
            scan(service,namespace)
            stat(service,namespace)
            scan_dict = read(service, namespace)
            if scan_dict != None:
                cpu_usage = deployment_cpu_percentage(namespace, service)
                upscale_deployment(service,namespace,0,cpu_usage)
                time.sleep(5)
                scan_dict['cpu_usage'] = cpu_usage
                results_dict[service] = scan_dict
            else:
                logging.info(f'{service} Have no vulnerabilities to be actioned')
        plan_dict = planning(results_dict)
        logging.info(f'<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<Iteration: {worker_loop_counter+1}')
        print_table(plan_dict)
        plan_dict = {key: val for key, val in plan_dict.items() if val.get('recommended') != 0}
        try:
            logging.info('Sending results to main')
            send_results(worker_id, plan_dict)
        except requests.exceptions.ConnectionError as e:
            logging.warning('Communication to Main lost, Local Plan will commence ... ')
            fallbackAction(plan_dict, worker_id, worker_loop_counter + 1, namespace)
            return  # Exit the function early to skip the rest of the code

        logging.info('Waiting for outcome')
        polling_attempts = 5  # Number of attempts to poll for decisions
        polling_count = 0  # Initial count of polling attempts

        while polling_count < polling_attempts:
            try:
                decisions = polling_for_decisions(worker_id)
                if decisions:
                    print_table(decisions)
                    action(decisions, worker_id, worker_loop_counter + 1, namespace)
                    break
                else:
                    polling_count += 1  
            except requests.exceptions.ConnectionError as e:
                logging.warning('Communication to Main lost, Local Plan will commence ... ')
                fallbackAction(plan_dict, worker_id, worker_loop_counter + 1, namespace)
                break  
            except Exception as e:
                logging.error(f'An unexpected error occurred: {e}')
                break  

            time.sleep(10) 
        else:
            logging.warning('Communication to Main lost, Local Plan will commence ... ')
            fallbackAction(plan_dict, worker_id, worker_loop_counter + 1, namespace)
        worker_loop_counter+=1
        logging.info(f'End of loop {worker_loop_counter}')
        time.sleep(5)
        

if __name__ == '__main__':   
    registration_data = register_worker() 
    if registration_data:
        worker_id = registration_data['worker_id']
        services = registration_data['services']
        namespace = registration_data['namespace']
        logging.info(f'This is {worker_id}')
        logging.info(f'Namespace {namespace}')
        logging.info(f'Deployment to monitor {services}')
        worker_mape()
    

wlog = logging.getLogger('werkzeug')
wlog.setLevel(logging.ERROR)
app.run(host='0.0.0.0', port=5000)
