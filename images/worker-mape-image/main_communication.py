from flask import Flask, jsonify
import requests
import logging 
from uuid import uuid4
from scanner import scan
from cpu_ut import deployment_cpu_percentage
from K_connection import action
logging.basicConfig(level=logging.INFO)
MAIN_MAPE_URL = 'http://main-mape-service.development.svc.cluster.local:80'

def register_worker():
    instance_id = str(uuid4()) 
    response = requests.post(f"{MAIN_MAPE_URL}/register", json={'instance_id': instance_id})
    if response.status_code == 200:
        return response.json()
    logging.error("Failed to register the worker.")
    return None

def send_results(worker_id, results_dict):
    data = {'worker_id': worker_id, 'results_dict': results_dict}
    try:
        response = requests.post(f"{MAIN_MAPE_URL}/results", json=data)
        response.raise_for_status()  
    except requests.exceptions.RequestException as e:
        pass 
    else:
        logging.info('Results sent successfully.')

def polling_for_decisions(worker_id):
    try:
        response = requests.get(f"{MAIN_MAPE_URL}/decisions/{worker_id}")
        response.raise_for_status()  
        return response.json()
    except requests.exceptions.RequestException as e:
        return None  
