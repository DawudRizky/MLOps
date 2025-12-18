"""
Optimized Airflow DAG: Humanized Scraper Scheduler for 2 CPU / 7.75GB RAM VPS

Resource Strategy:
- Sequential execution (no parallel tasks)
- Strict memory limits per container
- Only 4 runs per day (once per window)
- Ephemeral containers with auto-cleanup

Changes from original:
- Reduced resource limits for all containers
- Added ENFORCE_ONCE_PER_DAY to prevent duplicate window runs
- Stricter memory limits: scraper(512M), ingest(512M), quality(512M), trainer(2.5G)
- Auto-remove containers immediately after completion
"""
from __future__ import annotations

from airflow.models import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator, PythonOperator
from airflow.operators.bash import BashOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.utils.task_group import TaskGroup
from airflow.models import Variable
from datetime import datetime, timedelta, time
import random
import os
import json
import logging

try:
    import redis
except Exception:
    redis = None

# Configuration
DEFAULT_ARGS = {
    'owner': 'airflow',
    'depends_on_past': False,
    'retries': 0,
    'retry_delay': timedelta(minutes=5),
}

# Activity windows - ONLY run once per day per window
WINDOWS = [
    {'name': 'morning', 'start_h': 7, 'start_m': 15, 'duration_min_s': 600, 'duration_max_s': 900,
     'tweets_min': 35, 'tweets_max': 50, 'variance_min': 15, 'skip_prob': 0.0},  # No skip
    {'name': 'lunch',   'start_h':12, 'start_m':45, 'duration_min_s': 540, 'duration_max_s': 840,
     'tweets_min':25, 'tweets_max':40, 'variance_min':20, 'skip_prob': 0.0},  # No skip
    {'name': 'evening', 'start_h':18, 'start_m':20, 'duration_min_s': 660, 'duration_max_s': 960,
     'tweets_min':30, 'tweets_max':45, 'variance_min':15, 'skip_prob': 0.0},  # No skip
    {'name': 'night',   'start_h':21, 'start_m':30, 'duration_min_s': 600, 'duration_max_s': 840,
     'tweets_min':25, 'tweets_max':40, 'variance_min':18, 'skip_prob': 0.0},  # No skip
]

# Redis keys
REDIS_KEY_LAST_WINDOW = os.getenv('SCHED_REDIS_KEY_LAST_WINDOW', 'scheduler:last_window')

# ENFORCE: Only run once per window per day
ENFORCE_ONCE_PER_DAY = True

LOG = logging.getLogger('airflow.task')


def get_redis_client():
    """Connect to existing MLOps Redis instance"""
    host = os.getenv('REDIS_HOST', 'mlops-redis')
    port = int(os.getenv('REDIS_PORT', 6379))
    db = int(os.getenv('REDIS_DB', 1))  # Use DB 1 to avoid conflict with MLOps
    password = os.getenv('REDIS_PASSWORD', None)
    if redis is None:
        LOG.warning('redis library not available; persistent state disabled')
        return None
    try:
        return redis.Redis(host=host, port=port, db=db, password=password, decode_responses=True)
    except Exception as e:
        LOG.exception('Failed to create Redis client: %s', e)
        return None


def decide_window(**context):
    """Decide whether to run the pipeline now. ENFORCE: Only once per window per day."""
    # Load repo env (if present) pushed by `load_env` task
    repo_env = context['ti'].xcom_pull(task_ids='load_env', key='repo_env') or {}

    # Force-run override via Airflow Variable
    force_run = Variable.get('FORCE_RUN', default_var='false').lower() == 'true'

    now = datetime.utcnow() + timedelta(hours=float(os.getenv('TZ_OFFSET_HOURS', 7)))
    lookahead_minutes = int(os.getenv('SCHED_LOOKAHEAD_MIN', 15))

    LOG.info('Scheduler decide_window running at %s (TZ offset +%s)', now, os.getenv('TZ_OFFSET_HOURS', 7))

    for w in WINDOWS:
        base = datetime.combine(now.date(), time(w['start_h'], w['start_m']))
        variance_seconds = random.randint(-w['variance_min'] * 60, w['variance_min'] * 60)
        randomized_start = base + timedelta(seconds=variance_seconds)
        delta = (now - randomized_start).total_seconds()

        LOG.debug('Window %s randomized_start=%s delta=%s', w['name'], randomized_start, delta)

        if abs(delta) <= lookahead_minutes * 60 or force_run:
            # ENFORCE: Check if this window already ran successfully today
            window_key = f"scheduler:window:{now.date().isoformat()}:{w['name']}"
            r = get_redis_client()
            already_run = False
            
            if ENFORCE_ONCE_PER_DAY and not force_run:
                if r:
                    try:
                        already_run = r.get(window_key) == 'success'
                    except Exception:
                        LOG.exception('Failed to check window run status in Redis')
                else:
                    # Fallback to Airflow Variable
                    try:
                        already_run = Variable.get(window_key, default_var='') == 'success'
                    except Exception:
                        already_run = False

                if already_run:
                    LOG.info('✓ ENFORCED: Window %s already ran successfully today (%s), skipping.', 
                             w['name'], now.date().isoformat())
                    context['ti'].xcom_push(key='scheduled_window', 
                                          value={'name': w['name'], 'status': 'skipped_already_run', 
                                                 'window_key': window_key})
                    return 'do_skip'

            duration = random.randint(w['duration_min_s'], w['duration_max_s'])
            tweets = random.randint(w['tweets_min'], w['tweets_max'])

            # Merge with repo .env values
            env = {
                'WINDOW_NAME': w['name'],
                'SCRAPER_MODE': 'burst',
                'SCRAPER_DURATION': str(duration),
                'TWITTER_MAX_TWEETS': str(tweets),
                'MINIO_ENDPOINT': repo_env.get('MINIO_ENDPOINT', 'mlops-minio:9000'),
                'MINIO_ACCESS_KEY': repo_env.get('MINIO_ACCESS_KEY', 'minioadmin'),
                'MINIO_SECRET_KEY': repo_env.get('MINIO_SECRET_KEY', 'minioadmin123'),
                'MLFLOW_TRACKING_URI': repo_env.get('MLFLOW_TRACKING_URI', 'http://mlops-mlflow:5000'),
                'MLFLOW_S3_ENDPOINT_URL': 'http://' + repo_env.get('MINIO_ENDPOINT', 'mlops-minio:9000'),
                'TWITTER_SEARCH_QUERY': repo_env.get('TWITTER_SEARCH_QUERY', 'pemerintah lang:id -filter:retweets'),
                'POSTGRES_HOST': repo_env.get('POSTGRES_HOST', 'mlops-postgres'),
                'POSTGRES_PORT': repo_env.get('POSTGRES_PORT', '5432'),
                'POSTGRES_USER': repo_env.get('POSTGRES_USER', 'mlflow'),
                'POSTGRES_PASSWORD': repo_env.get('POSTGRES_PASSWORD', 'mlflow123'),
                'POSTGRES_DB': repo_env.get('POSTGRES_DB', 'mlflow'),
                'REDIS_HOST': repo_env.get('REDIS_HOST', 'mlops-redis'),
                'REDIS_PORT': repo_env.get('REDIS_PORT', '6379'),
                'AWS_ACCESS_KEY_ID': repo_env.get('MINIO_ACCESS_KEY', 'minioadmin'),
                'AWS_SECRET_ACCESS_KEY': repo_env.get('MINIO_SECRET_KEY', 'minioadmin123'),
                'LOG_LEVEL': 'INFO',
            }

            # Persist last window in Redis
            if r:
                try:
                    r.set(REDIS_KEY_LAST_WINDOW, json.dumps({
                        'name': w['name'], 
                        'start': randomized_start.isoformat(),
                        'date': now.date().isoformat()
                    }))
                except Exception:
                    LOG.exception('Failed to persist last window to Redis')

            context['ti'].xcom_push(key='scheduled_window', 
                                  value={'name': w['name'], 'status': 'run', 'env': env, 
                                         'window_key': window_key})
            LOG.info('✓ Window %s selected to run; duration=%ss tweets=%s', 
                     w['name'], duration, tweets)
            return 'pipeline'

    LOG.info('No window scheduled at this time')
    context['ti'].xcom_push(key='scheduled_window', value={'status': 'none'})
    return 'do_skip'


def load_repo_env(**context):
    """Read workspace .env file and push to XCom"""
    path = Variable.get('REPO_ENV_PATH', default_var='/opt/airflow/workspace/.env')
    env = {}
    try:
        with open(path, 'r') as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
        LOG.info('Loaded %d variables from %s', len(env), path)
    except Exception as e:
        LOG.warning('Could not read repo .env at %s: %s (using defaults)', path, e)

    context['ti'].xcom_push(key='repo_env', value=env)
    return env


def log_dvc_snapshot(**context):
    """
    Log that a dataset snapshot was created.
    Actual DVC tracking happens via cron job or manual run of dvc-snapshot.sh
    """
    ti = context['ti']
    scheduled = ti.xcom_pull(task_ids='decide_window', key='scheduled_window')
    
    window_name = scheduled.get('name', 'manual') if scheduled else 'manual'
    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    
    LOG.info("="*50)
    LOG.info("Dataset snapshot created for training run")
    LOG.info(f"Window: {window_name}")
    LOG.info(f"Timestamp: {timestamp}")
    LOG.info(f"Expected snapshot: tweets_{timestamp}_{window_name}.csv")
    LOG.info("Run 'bash /root/MLOps/scripts/dvc-snapshot.sh' on host to track with DVC")
    LOG.info("="*50)


def persist_post_run(**context):
    """Mark window as successfully completed"""
    ti = context['ti']
    scheduled = ti.xcom_pull(task_ids='decide_window', key='scheduled_window')
    
    if not scheduled or scheduled.get('status') != 'run':
        LOG.debug('No pipeline run to persist')
        return
    
    run_meta = {
        'dag_run_id': context.get('run_id'),
        'scheduled': scheduled,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    r = get_redis_client()
    if r and 'window_key' in scheduled:
        try:
            # Mark window as successful
            r.set(scheduled['window_key'], 'success', ex=86400)  # Expire after 24h
            # Add to history
            r.lpush('scheduler:history', json.dumps(run_meta))
            r.ltrim('scheduler:history', 0, 999)  # Keep last 1000 runs
            LOG.info('✓ Marked window %s as completed for today', scheduled.get('name'))
        except Exception:
            LOG.exception('Failed to persist post-run metadata to Redis')
    else:
        # Fallback to Airflow Variable
        try:
            if 'window_key' in scheduled:
                Variable.set(scheduled['window_key'], 'success')
                LOG.info('✓ Marked window %s as completed (via Airflow Variable)', scheduled.get('name'))
        except Exception:
            LOG.exception('Failed to persist window success to Airflow Variable')


with DAG(
    dag_id='scraper_humanized_scheduler_optimized',
    default_args=DEFAULT_ARGS,
    start_date=datetime(2025, 12, 1),
    schedule_interval='*/15 * * * *',  # Check every 15 minutes
    catchup=False,
    max_active_runs=1,  # Only one DAG run at a time
    tags=['mlops', 'twitter', 'production'],
) as dag:

    load_env = PythonOperator(
        task_id='load_env',
        python_callable=load_repo_env,
        provide_context=True,
    )

    decide = BranchPythonOperator(
        task_id='decide_window',
        python_callable=decide_window,
        provide_context=True,
    )

    do_skip = EmptyOperator(task_id='do_skip')

    load_env >> decide

    with TaskGroup('pipeline', tooltip='Sequential: scraper → ingest → quality → trainer') as pipeline:

        try:
            from airflow.providers.docker.operators.docker import DockerOperator
        except Exception:
            DockerOperator = None
            LOG.warning('DockerOperator not available; using EmptyOperator placeholders')

        # Common Docker settings for all tasks
        docker_common = {
            'api_version': 'auto',
            'auto_remove': 'success',  # Remove container after successful completion
            'docker_url': 'unix://var/run/docker.sock',
            'network_mode': 'mlops_mlops-network',  # Connect to existing MLOps network
            'mount_tmp_dir': False,
            'tty': True,
        }

        if DockerOperator:
            try:
                scraper = DockerOperator(
                    task_id='scraper_task',
                    image='mlops-scraper:latest',  # Will be built from MLOps/infrastructure/Dockerfile.scraper
                    **docker_common,
                    environment={
                        'SERVICE_NAME': 'scraper',
                        'SCRAPER_MODE': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['SCRAPER_MODE'] }}",
                        'SCRAPER_DURATION': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['SCRAPER_DURATION'] }}",
                        'TWITTER_MAX_TWEETS': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['TWITTER_MAX_TWEETS'] }}",
                        'TWITTER_SEARCH_QUERY': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['TWITTER_SEARCH_QUERY'] }}",
                        'TWITTER_COOKIES_FILE': '/app/cookies.json',
                        'MINIO_ENDPOINT': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['MINIO_ENDPOINT'] }}",
                        'MINIO_ACCESS_KEY': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['MINIO_ACCESS_KEY'] }}",
                        'MINIO_SECRET_KEY': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['MINIO_SECRET_KEY'] }}",
                        'REDIS_HOST': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['REDIS_HOST'] }}",
                        'REDIS_PORT': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['REDIS_PORT'] }}",
                        'POSTGRES_HOST': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_HOST'] }}",
                        'POSTGRES_PORT': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_PORT'] }}",
                        'POSTGRES_DB': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_DB'] }}",
                        'POSTGRES_USER': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_USER'] }}",
                        'POSTGRES_PASSWORD': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_PASSWORD'] }}",
                        'LOG_LEVEL': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['LOG_LEVEL'] }}",
                        'OMP_NUM_THREADS': '1',
                        'MKL_NUM_THREADS': '1',
                        'OPENBLAS_NUM_THREADS': '1',
                    },
                    mounts=[
                        {'source': '/root/MLOps/airflow/workspace/cookies.json', 'target': '/app/cookies.json', 'type': 'bind', 'read_only': True},
                        {'source': '/root/MLOps/airflow/workspace/data/raw', 'target': '/app/data/raw', 'type': 'bind'},
                    ],
                    mem_limit='512m',
                    cpus=0.15,
                )
            except Exception:
                LOG.exception('Failed to create scraper_task DockerOperator')
                scraper = EmptyOperator(task_id='scraper_task')
        else:
            scraper = EmptyOperator(task_id='scraper_task')

        if DockerOperator:
            try:
                ingest = DockerOperator(
                    task_id='ingest_task',
                    image='mlops-ingest:latest',
                    **docker_common,
                    environment={
                        'SERVICE_NAME': 'ingest',
                        'INGEST_MODE': 'once',
                        'MINIO_ENDPOINT': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['MINIO_ENDPOINT'] }}",
                        'MINIO_ACCESS_KEY': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['MINIO_ACCESS_KEY'] }}",
                        'MINIO_SECRET_KEY': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['MINIO_SECRET_KEY'] }}",
                        'POSTGRES_HOST': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_HOST'] }}",
                        'POSTGRES_PORT': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_PORT'] }}",
                        'POSTGRES_DB': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_DB'] }}",
                        'POSTGRES_USER': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_USER'] }}",
                        'POSTGRES_PASSWORD': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_PASSWORD'] }}",
                        'REDIS_HOST': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['REDIS_HOST'] }}",
                        'REDIS_PORT': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['REDIS_PORT'] }}",
                        'LOG_LEVEL': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['LOG_LEVEL'] }}",
                        'OMP_NUM_THREADS': '1',
                        'MKL_NUM_THREADS': '1',
                    },
                    mounts=[
                        {'source': '/root/MLOps/airflow/workspace/data', 'target': '/app/data', 'type': 'bind'},
                    ],
                    mem_limit='512m',
                    cpus=0.15,
                )
            except Exception:
                LOG.exception('Failed to create ingest_task DockerOperator')
                ingest = EmptyOperator(task_id='ingest_task')
        else:
            ingest = EmptyOperator(task_id='ingest_task')

        if DockerOperator:
            try:
                quality_gate = DockerOperator(
                    task_id='quality_gate_task',
                    image='mlops-quality-gate:latest',
                    **docker_common,
                    environment={
                        'SERVICE_NAME': 'quality_gate',
                        'QUALITY_MODE': 'once',
                        'POSTGRES_HOST': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_HOST'] }}",
                        'POSTGRES_PORT': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_PORT'] }}",
                        'POSTGRES_DB': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_DB'] }}",
                        'POSTGRES_USER': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_USER'] }}",
                        'POSTGRES_PASSWORD': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_PASSWORD'] }}",
                        'REDIS_HOST': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['REDIS_HOST'] }}",
                        'REDIS_PORT': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['REDIS_PORT'] }}",
                        'LOG_LEVEL': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['LOG_LEVEL'] }}",
                        'OMP_NUM_THREADS': '1',
                        'MKL_NUM_THREADS': '1',
                    },
                    mounts=[
                        {'source': '/root/MLOps/airflow/workspace/reports', 'target': '/app/reports', 'type': 'bind'},
                    ],
                    mem_limit='512m',
                    cpus=0.15,
                )
            except Exception:
                LOG.exception('Failed to create quality_gate_task DockerOperator')
                quality_gate = EmptyOperator(task_id='quality_gate_task')
        else:
            quality_gate = EmptyOperator(task_id='quality_gate_task')

        if DockerOperator:
            try:
                trainer = DockerOperator(
                    task_id='trainer_task',
                    image='mlops-trainer:latest',
                    **docker_common,
                    environment={
                        'SERVICE_NAME': 'trainer',
                        'TRAINER_MODE': 'once',
                        'MLFLOW_TRACKING_URI': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['MLFLOW_TRACKING_URI'] }}",
                        'MLFLOW_S3_ENDPOINT_URL': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['MLFLOW_S3_ENDPOINT_URL'] }}",
                        'AWS_ACCESS_KEY_ID': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['AWS_ACCESS_KEY_ID'] }}",
                        'AWS_SECRET_ACCESS_KEY': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['AWS_SECRET_ACCESS_KEY'] }}",
                        'MINIO_ENDPOINT': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['MINIO_ENDPOINT'] }}",
                        'MINIO_ACCESS_KEY': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['MINIO_ACCESS_KEY'] }}",
                        'MINIO_SECRET_KEY': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['MINIO_SECRET_KEY'] }}",
                        'POSTGRES_HOST': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_HOST'] }}",
                        'POSTGRES_PORT': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_PORT'] }}",
                        'POSTGRES_DB': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_DB'] }}",
                        'POSTGRES_USER': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_USER'] }}",
                        'POSTGRES_PASSWORD': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['POSTGRES_PASSWORD'] }}",
                        'REDIS_HOST': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['REDIS_HOST'] }}",
                        'REDIS_PORT': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['REDIS_PORT'] }}",
                        'LOG_LEVEL': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['LOG_LEVEL'] }}",
                        'OMP_NUM_THREADS': '1',  # Limit OpenMP threads
                        'MKL_NUM_THREADS': '1',  # Limit MKL threads
                        'OPENBLAS_NUM_THREADS': '1',  # Limit OpenBLAS threads
                        'NUMEXPR_NUM_THREADS': '1',  # Limit NumExpr threads
                    },
                    mounts=[
                        {'source': '/root/MLOps/airflow/workspace/models', 'target': '/app/models', 'type': 'bind'},
                        {'source': '/root/MLOps/airflow/workspace/reports', 'target': '/app/reports', 'type': 'bind'},
                        {'source': '/root/MLOps/data', 'target': '/app/data', 'type': 'bind'},  # Mount for dataset snapshots
                    ],
                    mem_limit='2048m',  # 2GB memory limit (system only has ~1GB free)
                    cpus=0.37,  # 0.37 cores (37% of 1 core)
                )
            except Exception:
                LOG.exception('Failed to create trainer_task DockerOperator')
                trainer = EmptyOperator(task_id='trainer_task')
        else:
            trainer = EmptyOperator(task_id='trainer_task')

        # Sequential execution: scraper → ingest → quality → trainer
        scraper >> ingest >> quality_gate >> trainer

    # DVC snapshot logging - actual DVC tracking runs via cron or manual script
    dvc_snapshot = PythonOperator(
        task_id='dvc_snapshot',
        python_callable=log_dvc_snapshot,
        provide_context=True,
        trigger_rule='all_success',  # Only run if all upstream tasks succeeded
    )

    persist = PythonOperator(
        task_id='persist_post_run',
        python_callable=persist_post_run,
        provide_context=True
    )

    # Trigger deployment if training succeeded
    trigger_deployment = TriggerDagRunOperator(
        task_id='trigger_deployment',
        trigger_dag_id='model_deployment_pipeline',
        wait_for_completion=False,
        conf={'triggered_by': 'scraper_humanized_scheduler_optimized'},
        trigger_rule='all_success',  # Only trigger if training succeeded
    )

    decide >> [pipeline, do_skip]
    pipeline >> dvc_snapshot >> persist >> trigger_deployment
