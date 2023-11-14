
from flask import Flask, request, jsonify,render_template
from flask_restful import Resource, Api, reqparse
from collections import defaultdict
import pandas as pd
import subprocess
import logging
import json

logging.basicConfig(level=logging.INFO)

#<<<<<<<<<<<<<<< Main API >>>>>>>>>>>>>>>>>>>>>
app = Flask(__name__)
api = Api(app)

class DataManager:
    def __init__(self):
        self.received_data = defaultdict(dict)
        self.decisions = {}
        self.counter = 0
        self.main_loop_counter = 0
        self.workers = {}
        self.namespace = 'online-boutique'
        self.services = self.list_services(self.namespace)
        self.expected_number_of_workers = 3
        self.received_counter = 0
        self.service_batches = [self.services[i::self.expected_number_of_workers] for i in range(self.expected_number_of_workers)]

    def process_and_make_decisions(self):
        self.decisions.clear()
        combined_dict = {}
        for worker_data in self.received_data.values():
            combined_dict.update(worker_data)
        sorted_items = sorted(combined_dict.items(), key=lambda x: x[1].get('cpu_usage', 0), reverse=True)
        split_index = len(sorted_items) // 2
        for i, (service, data) in enumerate(sorted_items):
            decision_value = 1 if i < split_index else 0
            self.decisions[service] = {
                'serviceName': data.get('serviceName'),
                'totalRisk': data.get('totalRisk',None),
                'topCVE': data.get('topCVE', None),
                'mitigation': data.get('mitigation', None),
                'cpu_usage': data.get('cpu_usage',None),
                'recommended':data.get('recommended',None),
                'decision': decision_value
            }
        self.received_data.clear()
        self.counter += 1

    def print_table(self,data):
        data_list = list(data.values())
        df = pd.DataFrame(data_list)
        table_string = df.to_string(index=False)
        logging.info('\n' + table_string)

    def list_services(self,namespace):
        command = f"kubectl get deployment -n {namespace} -o jsonpath='{{.items[*].metadata.name}}'"
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            pod_names = result.stdout.strip().split()
            return pod_names
        else:
            logging.error("Failed to get pods. Error: %s", result.stderr)
        return []

data_manager = DataManager()

class Results(Resource):
    def post(self):
        data = request.get_json()
        worker_id = data.get('worker_id')
        results_dict = data.get('results_dict')
        if worker_id is not None and results_dict is not None:
            data_manager.received_data[worker_id] = results_dict
            data_manager.received_counter += 1
            if data_manager.received_counter >= data_manager.expected_number_of_workers:
                data_manager.process_and_make_decisions()
                data_manager.received_counter = 0 
            return {'status': 'acknowledged'}, 200
        return {'error': 'Invalid data format'}, 400

class Decisions(Resource):
    def get(self, worker_id):
        worker_services = data_manager.workers.get(worker_id, {}).get('services', [])
        filtered_decisions = {service: decision for service, decision in data_manager.decisions.items() if service in worker_services}
        return filtered_decisions, 200
    
class UpdateConfig(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('expected_number_of_workers', type=int, required=False)
    parser.add_argument('namespace', type=str, required=False)

    def post(self):
        args = self.parser.parse_args()
        updated_fields = {}
        
        if args['expected_number_of_workers'] is not None:
            data_manager.expected_number_of_workers = args['expected_number_of_workers']
            updated_fields['expected_number_of_workers'] = args['expected_number_of_workers']
            data_manager.service_batches = [data_manager.services[i::data_manager.expected_number_of_workers] for i in range(data_manager.expected_number_of_workers)]
        
        if args['namespace']:
            data_manager.namespace = args['namespace']
            updated_fields['namespace'] = args['namespace']
        
        if updated_fields:
            return {'updated_fields': updated_fields}, 200
        else:
            return {'error': 'No valid fields provided for update'}, 400

class RegisterWorker(Resource):
    worker_count = 0
    
    def post(self):
        #logging.info(f'Registration attempt: {request.json}')
        if not request.json or 'instance_id' not in request.json:
            return {'error': 'instance_id is required'}, 400
        
        instance_id = request.json['instance_id']
        if RegisterWorker.worker_count >= data_manager.expected_number_of_workers or RegisterWorker.worker_count >= len(data_manager.service_batches):
            return {'error': 'All services have been assigned, no more workers needed'}, 400
        
        assigned_services = data_manager.service_batches[RegisterWorker.worker_count]
        worker_id = f"worker-{RegisterWorker.worker_count + 1}"
        data_manager.workers[worker_id] = {'instance_id': instance_id, 'services': assigned_services, 'decisions': []}
        
        RegisterWorker.worker_count += 1
        
        return {'worker_id': worker_id, 'services': assigned_services , 'namespace':data_manager.namespace}, 200

api.add_resource(RegisterWorker, '/register')
api.add_resource(Results, '/results')
api.add_resource(Decisions, '/decisions/<string:worker_id>')
api.add_resource(UpdateConfig, '/update_config')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)