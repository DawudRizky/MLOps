"""
Model Deployment DAG with Blue-Green Strategy

Automatically deploys new models to production using blue-green deployment
when a new model is successfully trained and validated.

Workflow:
1. Check for new model in MLflow
2. Validate model metrics
3. Build new Docker images (green)
4. Deploy to green environment
5. Run health checks and smoke tests
6. Switch traffic to green (zero downtime)
7. Stop old blue deployment
8. Promote green to blue for next deployment

Author: MLOps Team
"""

import os
import logging
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.task_group import TaskGroup
from airflow.models import Variable
import requests

# Logging
LOG = logging.getLogger(__name__)

# Default args
default_args = {
    'owner': 'mlops-team',
    'depends_on_past': False,
    'start_date': datetime(2025, 12, 18),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=2),
}

# DAG definition
dag = DAG(
    'model_deployment_pipeline',
    default_args=default_args,
    description='Automated model deployment with blue-green strategy',
    schedule_interval=None,  # Triggered by external event or manually
    catchup=False,
    max_active_runs=1,
    tags=['deployment', 'blue-green', 'mlops', 'production'],
)


def check_new_model(**context):
    """
    Check MLflow for new model that needs deployment.
    Returns the latest run ID and model URI.
    """
    mlflow_uri = os.getenv('MLFLOW_TRACKING_URI', 'http://mlops-mlflow:5000')
    experiment_name = Variable.get('mlflow_experiment_name', 'bertopic-pemerintah')
    
    LOG.info(f"Checking MLflow at {mlflow_uri} for experiment: {experiment_name}")
    
    try:
        # Get latest successful run
        response = requests.post(
            f"{mlflow_uri}/api/2.0/mlflow/runs/search",
            json={
                "experiment_names": [experiment_name],
                "filter": "attributes.status = 'FINISHED'",
                "order_by": ["attributes.start_time DESC"],
                "max_results": 1
            }
        )
        response.raise_for_status()
        
        runs = response.json().get('runs', [])
        if not runs:
            LOG.warning("No finished runs found")
            return None
        
        latest_run = runs[0]
        run_id = latest_run['info']['run_id']
        
        # Get model metrics
        metrics = {m['key']: m['value'] for m in latest_run['data']['metrics']}
        
        LOG.info(f"Latest run: {run_id}")
        LOG.info(f"Metrics: {metrics}")
        
        # Check if model meets deployment criteria
        min_coherence = float(Variable.get('min_coherence_score', '0.3'))
        coherence = metrics.get('coherence_score', 0)
        
        if coherence < min_coherence:
            LOG.warning(f"Model coherence {coherence} below threshold {min_coherence}")
            return None
        
        # Store run info in XCom
        model_info = {
            'run_id': run_id,
            'model_uri': f"runs:/{run_id}/model",
            'metrics': metrics,
            'artifact_uri': latest_run['info']['artifact_uri']
        }
        
        context['ti'].xcom_push(key='model_info', value=model_info)
        LOG.info(f"Model ready for deployment: {model_info}")
        
        return model_info
        
    except Exception as e:
        LOG.error(f"Failed to check MLflow: {e}")
        raise


def decide_deployment(**context):
    """Decide whether to proceed with deployment or skip."""
    model_info = context['ti'].xcom_pull(task_ids='check_new_model_task', key='model_info')
    
    if model_info:
        LOG.info("New model found, proceeding with deployment")
        return 'prepare_deployment'
    else:
        LOG.info("No new model to deploy, skipping")
        return 'skip_deployment'


def get_current_deployment(**context):
    """Get current active deployment (blue or green)."""
    import subprocess
    
    result = subprocess.run(
        ['grep', 'ACTIVE_DEPLOYMENT=', '/root/MLOps/.env'],
        capture_output=True,
        text=True
    )
    
    current = result.stdout.split('=')[1].strip() if result.returncode == 0 else 'blue'
    target = 'green' if current == 'blue' else 'blue'
    
    LOG.info(f"Current deployment: {current}, Target: {target}")
    
    context['ti'].xcom_push(key='current_deployment', value=current)
    context['ti'].xcom_push(key='target_deployment', value=target)
    
    return {'current': current, 'target': target}


def validate_model_locally(**context):
    """
    Run local validation tests on the model before deploying.
    This can include:
    - Model loading test
    - Inference latency test
    - Output format validation
    """
    model_info = context['ti'].xcom_pull(task_ids='check_new_model_task', key='model_info')
    
    LOG.info(f"Validating model: {model_info['run_id']}")
    
    # TODO: Add actual validation logic
    # For now, just check if metrics are present
    if not model_info.get('metrics'):
        raise ValueError("Model has no metrics")
    
    LOG.info("Model validation passed")
    return True


# ========================================
# DAG Tasks
# ========================================

with dag:
    
    start = EmptyOperator(task_id='start')
    
    # Check for new model
    check_new_model = PythonOperator(
        task_id='check_new_model_task',
        python_callable=check_new_model,
        provide_context=True,
    )
    
    # Decide deployment
    decide = BranchPythonOperator(
        task_id='decide_deployment',
        python_callable=decide_deployment,
        provide_context=True,
    )
    
    skip_deployment = EmptyOperator(task_id='skip_deployment')
    
    # Prepare deployment
    prepare_deployment = PythonOperator(
        task_id='prepare_deployment',
        python_callable=get_current_deployment,
        provide_context=True,
    )
    
    # Validate model
    validate_model = PythonOperator(
        task_id='validate_model',
        python_callable=validate_model_locally,
        provide_context=True,
    )
    
    # Build Docker images for target deployment
    build_images = BashOperator(
        task_id='build_images',
        bash_command="""
        cd /root/MLOps
        TARGET="{{ ti.xcom_pull(task_ids='prepare_deployment', key='target_deployment') }}"
        echo "Building images for $TARGET deployment..."
        
        # Build dashboard
        docker compose build dashboard-$TARGET
        
        # Tag with timestamp
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        docker tag mlops-dashboard-$TARGET:latest mlops-dashboard-$TARGET:$TIMESTAMP
        
        echo "Build complete: mlops-dashboard-$TARGET:$TIMESTAMP"
        """,
    )
    
    # Deploy to target environment
    deploy_target = BashOperator(
        task_id='deploy_target',
        bash_command="""
        cd /root/MLOps
        TARGET="{{ ti.xcom_pull(task_ids='prepare_deployment', key='target_deployment') }}"
        
        echo "Deploying to $TARGET environment..."
        
        if [ "$TARGET" == "green" ]; then
            docker compose --profile green up -d dashboard-green
        else
            docker compose up -d dashboard-blue
        fi
        
        echo "Waiting for container to start..."
        sleep 10
        """,
    )
    
    # Health check on target
    health_check = BashOperator(
        task_id='health_check_target',
        bash_command="""
        TARGET="{{ ti.xcom_pull(task_ids='prepare_deployment', key='target_deployment') }}"
        PORT=$([ "$TARGET" == "blue" ] && echo "8003" || echo "8004")
        
        echo "Running health check on $TARGET (port $PORT)..."
        
        MAX_ATTEMPTS=30
        ATTEMPT=1
        
        while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
            if curl -sf "http://localhost:$PORT/api/health" > /dev/null 2>&1; then
                echo "Health check passed for $TARGET"
                exit 0
            fi
            
            echo "Attempt $ATTEMPT/$MAX_ATTEMPTS failed, retrying..."
            sleep 2
            ATTEMPT=$((ATTEMPT + 1))
        done
        
        echo "Health check failed for $TARGET"
        exit 1
        """,
        retries=0,  # Don't retry bash failures, the bash script has its own retry logic
    )
    
    # Run smoke tests
    smoke_tests = BashOperator(
        task_id='smoke_tests',
        bash_command="""
        TARGET="{{ ti.xcom_pull(task_ids='prepare_deployment', key='target_deployment') }}"
        PORT=$([ "$TARGET" == "blue" ] && echo "8003" || echo "8004")
        
        echo "Running smoke tests on $TARGET (port $PORT)..."
        
        # Test wordcloud endpoint
        echo "Testing /api/wordcloud..."
        if ! curl -sf "http://localhost:$PORT/api/wordcloud" | jq -e '.[0].text' > /dev/null; then
            echo "Wordcloud test failed"
            exit 1
        fi
        
        # Test sentiment endpoint
        echo "Testing /api/sentiment..."
        if ! curl -sf "http://localhost:$PORT/api/sentiment" | jq -e '.[0]' > /dev/null; then
            echo "Sentiment test failed"
            exit 1
        fi
        
        # Test topic-info endpoint
        echo "Testing /api/topic-info..."
        if ! curl -sf "http://localhost:$PORT/api/topic-info" | jq -e '.topics' > /dev/null; then
            echo "Topic info test failed"
            exit 1
        fi
        
        echo "All smoke tests passed!"
        """,
    )
    
    # Switch traffic to target (blue-green switch)
    switch_traffic = BashOperator(
        task_id='switch_traffic',
        bash_command="""
        cd /root/MLOps
        TARGET="{{ ti.xcom_pull(task_ids='prepare_deployment', key='target_deployment') }}"
        
        echo "Switching traffic to $TARGET deployment..."
        
        # Copy target config to active
        cp infrastructure/configs/nginx-$TARGET.conf infrastructure/configs/nginx-active.conf
        
        # Reload nginx
        if docker ps | grep -q mlops-nginx; then
            docker exec mlops-nginx nginx -s reload
            echo "Nginx reloaded successfully"
        else
            echo "Starting nginx..."
            docker compose up -d nginx
            sleep 3
        fi
        
        # Verify nginx is routing correctly
        if curl -sf "http://localhost/" > /dev/null 2>&1; then
            echo "Traffic switched successfully to $TARGET"
        else
            echo "Traffic switch verification failed"
            exit 1
        fi
        """,
    )
    
    # Update .env to mark new active deployment
    update_env = BashOperator(
        task_id='update_env',
        bash_command="""
        TARGET="{{ ti.xcom_pull(task_ids='prepare_deployment', key='target_deployment') }}"
        
        echo "Updating ACTIVE_DEPLOYMENT to $TARGET in .env..."
        sed -i "s/^ACTIVE_DEPLOYMENT=.*/ACTIVE_DEPLOYMENT=$TARGET/" /root/MLOps/.env
        
        echo "Updated .env: ACTIVE_DEPLOYMENT=$TARGET"
        """,
    )
    
    # Stop old deployment
    stop_old = BashOperator(
        task_id='stop_old_deployment',
        bash_command="""
        cd /root/MLOps
        CURRENT="{{ ti.xcom_pull(task_ids='prepare_deployment', key='current_deployment') }}"
        
        echo "Stopping old $CURRENT deployment..."
        docker compose stop dashboard-$CURRENT
        
        echo "Old deployment stopped successfully"
        """,
    )
    
    # Deployment success
    deployment_success = EmptyOperator(
        task_id='deployment_success',
        trigger_rule='none_failed',
    )
    
    # DVC model snapshot - version models after successful deployment
    dvc_model_snapshot = BashOperator(
        task_id='dvc_model_snapshot',
        bash_command='bash /root/MLOps/scripts/dvc-model-snapshot.sh {{ var.value.mlflow_experiment_name }}',
        trigger_rule='all_success',
    )
    
    # DVC model cleanup - keep only 2 latest versions
    dvc_model_cleanup = BashOperator(
        task_id='dvc_model_cleanup',
        bash_command='bash /root/MLOps/scripts/dvc-model-cleanup.sh',
        trigger_rule='all_success',
    )
    
    # Rollback task (in case of failure)
    rollback = BashOperator(
        task_id='rollback',
        bash_command="""
        cd /root/MLOps
        CURRENT="{{ ti.xcom_pull(task_ids='prepare_deployment', key='current_deployment') }}"
        TARGET="{{ ti.xcom_pull(task_ids='prepare_deployment', key='target_deployment') }}"
        
        echo "ROLLBACK: Deployment to $TARGET failed, reverting to $CURRENT..."
        
        # Stop failed target deployment
        docker compose stop dashboard-$TARGET
        
        # Ensure current deployment is running
        docker compose up -d dashboard-$CURRENT
        sleep 5
        
        # Restore nginx config
        cp infrastructure/configs/nginx-$CURRENT.conf infrastructure/configs/nginx-active.conf
        docker exec mlops-nginx nginx -s reload || docker restart mlops-nginx
        
        echo "Rollback complete, $CURRENT is active"
        """,
        trigger_rule='one_failed',
    )
    
    end = EmptyOperator(
        task_id='end',
        trigger_rule='none_failed_min_one_success',
    )

    # ========================================
    # Task Dependencies
    # ========================================
    
    start >> check_new_model >> decide
    
    # Branch: deploy or skip
    decide >> [prepare_deployment, skip_deployment]
    
    # Deployment path
    prepare_deployment >> validate_model >> build_images >> deploy_target
    deploy_target >> health_check >> smoke_tests >> switch_traffic
    switch_traffic >> update_env >> stop_old >> deployment_success
    
    # DVC model versioning after successful deployment
    deployment_success >> dvc_model_snapshot >> dvc_model_cleanup >> end
    
    # Skip path
    skip_deployment >> end
    
    # Rollback on failure (attach to critical tasks)
    [health_check, smoke_tests, switch_traffic] >> rollback >> end
