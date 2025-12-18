"""
Model Training Watcher DAG

Monitors MLflow for new model training completions and triggers deployment DAG.
This creates a complete CI/CD pipeline: Train → Validate → Deploy

Author: MLOps Team
"""

import os
import logging
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.operators.empty import EmptyOperator
from airflow.models import Variable
import requests

LOG = logging.getLogger(__name__)

default_args = {
    'owner': 'mlops-team',
    'depends_on_past': False,
    'start_date': datetime(2025, 12, 18),
    'email_on_failure': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'model_training_watcher',
    default_args=default_args,
    description='Watches for model training completion and triggers deployment',
    schedule_interval='*/15 * * * *',  # Check every 15 minutes
    catchup=False,
    max_active_runs=1,
    tags=['watcher', 'mlops', 'ci-cd'],
)


def check_for_new_trained_model(**context):
    """
    Check if there's a new model trained since last check.
    Returns True if deployment should be triggered.
    """
    mlflow_uri = os.getenv('MLFLOW_TRACKING_URI', 'http://mlops-mlflow:5000')
    experiment_name = Variable.get('mlflow_experiment_name', 'bertopic-pemerintah')
    
    # Get last checked timestamp
    last_checked = Variable.get('last_deployment_check', default_var=None)
    
    try:
        # Get latest run
        response = requests.get(
            f"{mlflow_uri}/api/2.0/mlflow/runs/search",
            json={
                "experiment_names": [experiment_name],
                "filter": "attributes.status = 'FINISHED'",
                "order_by": ["attributes.start_time DESC"],
                "max_results": 1
            },
            timeout=10
        )
        response.raise_for_status()
        
        runs = response.json().get('runs', [])
        if not runs:
            LOG.info("No finished runs found")
            return False
        
        latest_run = runs[0]
        run_id = latest_run['info']['run_id']
        end_time = latest_run['info']['end_time']  # milliseconds since epoch
        
        # Check if this is a new run since last check
        if last_checked:
            last_checked_ms = int(float(last_checked))
            if end_time <= last_checked_ms:
                LOG.info(f"No new model since {datetime.fromtimestamp(last_checked_ms/1000)}")
                return False
        
        # Check if model meets deployment criteria
        metrics = {m['key']: m['value'] for m in latest_run['data']['metrics']}
        min_coherence = float(Variable.get('min_coherence_score', '0.3'))
        coherence = metrics.get('coherence_score', 0)
        
        if coherence < min_coherence:
            LOG.warning(f"Model {run_id} coherence {coherence} below threshold {min_coherence}")
            Variable.set('last_deployment_check', str(end_time))
            return False
        
        LOG.info(f"New deployable model found: {run_id} with coherence {coherence}")
        LOG.info(f"Metrics: {metrics}")
        
        # Update last checked timestamp
        Variable.set('last_deployment_check', str(end_time))
        
        # Store run info for deployment DAG
        context['ti'].xcom_push(key='new_model_run_id', value=run_id)
        context['ti'].xcom_push(key='new_model_metrics', value=metrics)
        
        return True
        
    except requests.exceptions.RequestException as e:
        LOG.error(f"Failed to connect to MLflow: {e}")
        return False
    except Exception as e:
        LOG.error(f"Error checking for new model: {e}")
        raise


with dag:
    start = EmptyOperator(task_id='start')
    
    check_model = PythonOperator(
        task_id='check_for_new_model',
        python_callable=check_for_new_trained_model,
        provide_context=True,
    )
    
    trigger_deployment = TriggerDagRunOperator(
        task_id='trigger_deployment',
        trigger_dag_id='model_deployment_pipeline',
        wait_for_completion=False,  # Don't wait, let it run async
        conf={
            'triggered_by': 'model_training_watcher',
            'run_id': "{{ ti.xcom_pull(task_ids='check_for_new_model', key='new_model_run_id') }}"
        },
    )
    
    no_deployment = EmptyOperator(task_id='no_deployment_needed')
    
    end = EmptyOperator(
        task_id='end',
        trigger_rule='none_failed_min_one_success'
    )
    
    # Use Python branching
    def should_trigger_deployment(**context):
        """Branching logic based on check_model result."""
        result = context['ti'].xcom_pull(task_ids='check_for_new_model')
        return 'trigger_deployment' if result else 'no_deployment_needed'
    
    branch = PythonOperator(
        task_id='branch_on_new_model',
        python_callable=should_trigger_deployment,
        provide_context=True,
    )
    
    start >> check_model >> branch
    branch >> [trigger_deployment, no_deployment]
    [trigger_deployment, no_deployment] >> end
