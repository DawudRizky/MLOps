"""
Airflow DAG: Humanized Scraper Scheduler

Features:
- Human-like activity windows with randomized start times, duration, tweet counts
- Branching to either run the pipeline or skip based on window logic
- Pass dynamic environment variables to DockerOperator tasks via XCom templating
- Persist scheduler state between runs in Redis (optional, configurable via env)

Notes:
- This DAG expects the Airflow worker to have access to Docker (docker.sock) and host paths.
- Credentials and sensitive values should be stored in Airflow Connections/Variables in production.
"""
from __future__ import annotations

from airflow.models import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator, PythonOperator
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

# Activity windows (mirrors your custom scheduler)
WINDOWS = [
    {'name': 'morning', 'start_h': 7, 'start_m': 15, 'duration_min_s': 600, 'duration_max_s': 900,
     'tweets_min': 35, 'tweets_max': 50, 'variance_min': 15, 'skip_prob': 0.05},
    {'name': 'lunch',   'start_h':12, 'start_m':45, 'duration_min_s': 540, 'duration_max_s': 840,
     'tweets_min':25, 'tweets_max':40, 'variance_min':20, 'skip_prob': 0.08},
    {'name': 'evening', 'start_h':18, 'start_m':20, 'duration_min_s': 660, 'duration_max_s': 960,
     'tweets_min':30, 'tweets_max':45, 'variance_min':15, 'skip_prob': 0.06},
    {'name': 'night',   'start_h':21, 'start_m':30, 'duration_min_s': 600, 'duration_max_s': 840,
     'tweets_min':25, 'tweets_max':40, 'variance_min':18, 'skip_prob': 0.10},
]

# Redis keys
REDIS_KEY_LAST_WINDOW = os.getenv('SCHED_REDIS_KEY_LAST_WINDOW', 'scheduler:last_window')

LOG = logging.getLogger('airflow.task')


def get_redis_client():
    host = os.getenv('REDIS_HOST', 'redis')
    port = int(os.getenv('REDIS_PORT', 6379))
    db = int(os.getenv('REDIS_DB', 0))
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
    """Decide whether to run the pipeline now. Push dynamic env to XCom key 'env'."""
    # Load repo env (if present) pushed by `load_env` task
    repo_env = context['ti'].xcom_pull(task_ids='load_env', key='repo_env') or {}

    # Force-run override via Airflow Variable
    force_run = Variable.get('FORCE_RUN', default_var='false').lower() == 'true'

    now = datetime.utcnow() + timedelta(hours=float(os.getenv('TZ_OFFSET_HOURS', 0)))
    lookahead_minutes = int(os.getenv('SCHED_LOOKAHEAD_MIN', 15))

    LOG.info('Scheduler decide_window running at %s (UTC offset %s)', now, os.getenv('TZ_OFFSET_HOURS', 0))

    for w in WINDOWS:
        base = datetime.combine(now.date(), time(w['start_h'], w['start_m']))
        variance_seconds = random.randint(-w['variance_min'] * 60, w['variance_min'] * 60)
        randomized_start = base + timedelta(seconds=variance_seconds)
        delta = (now - randomized_start).total_seconds()

        LOG.debug('Window %s randomized_start=%s delta=%s', w['name'], randomized_start, delta)

        if abs(delta) <= lookahead_minutes * 60 or force_run:
            # Check if a successful run for this window already exists
            window_key = f"scheduler:window:{now.date().isoformat()}:{w['name']}"
            r = get_redis_client()
            already_run = False
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

            if already_run and not force_run:
                LOG.info('ENFORCED: Window %s already has a successful run for %s, skipping this run.', w['name'], now.date().isoformat())
                context['ti'].xcom_push(key='scheduled_window', value={'name': w['name'], 'status': 'skipped_already_run', 'window_key': window_key})
                return 'do_skip'

            # Decide whether to skip
            if not force_run and random.random() < w['skip_prob']:
                LOG.info('Window %s skipped by probability', w['name'])
                context['ti'].xcom_push(key='scheduled_window', value={'name': w['name'], 'status': 'skipped', 'window_key': window_key})
                return 'do_skip'

            duration = random.randint(w['duration_min_s'], w['duration_max_s'])
            tweets = random.randint(w['tweets_min'], w['tweets_max'])

            # Merge with repo .env values (repo_env takes precedence when present)
            env = {
                'WINDOW_NAME': w['name'],
                'SCRAPER_MODE': 'burst',
                'SCRAPER_DURATION': str(duration),
                'TWITTER_MAX_TWEETS': str(tweets),
                'MINIO_ENDPOINT': repo_env.get('MINIO_ENDPOINT', 'minio:9000'),
                'MINIO_ACCESS_KEY': repo_env.get('MINIO_ACCESS_KEY'),
                'MINIO_SECRET_KEY': repo_env.get('MINIO_SECRET_KEY'),
                'MLFLOW_TRACKING_URI': repo_env.get('MLFLOW_TRACKING_URI', 'http://mlflow:5000'),
                'MLFLOW_S3_ENDPOINT_URL': 'http://' + repo_env.get('MINIO_ENDPOINT', 'minio:9000'),
                'TWITTER_SEARCH_QUERY': repo_env.get('TWITTER_SEARCH_QUERY', 'pemerintah lang:id -filter:retweets'),
                'POSTGRES_HOST': repo_env.get('POSTGRES_HOST', 'postgres'),
                'POSTGRES_PORT': repo_env.get('POSTGRES_PORT', '5432'),
                'POSTGRES_USER': repo_env.get('POSTGRES_USER'),
                'POSTGRES_PASSWORD': repo_env.get('POSTGRES_PASSWORD'),
                'POSTGRES_DB': repo_env.get('POSTGRES_DB'),
                'REDIS_HOST': repo_env.get('REDIS_HOST', 'redis'),
                'REDIS_PORT': repo_env.get('REDIS_PORT', '6379'),
                'LOG_LEVEL': 'INFO',
            }

            # Persist last window in Redis (best-effort)
            if r:
                try:
                    r.set(REDIS_KEY_LAST_WINDOW, json.dumps({'name': w['name'], 'start': randomized_start.isoformat()}))
                except Exception:
                    LOG.exception('Failed to persist last window to Redis')

            context['ti'].xcom_push(key='scheduled_window', value={'name': w['name'], 'status': 'run', 'env': env, 'window_key': window_key})
            LOG.info('Window %s selected to run; env=%s', w['name'], {k: env[k] for k in ['SCRAPER_DURATION','TWITTER_MAX_TWEETS']})
            return 'pipeline'

    LOG.info('No window scheduled at this time')
    context['ti'].xcom_push(key='scheduled_window', value={'status': 'none'})
    return 'do_skip'


def load_repo_env(**context):
    """Read a repository `.env` file (path from Airflow Variable `REPO_ENV_PATH`) and push key/value map to XCom as `repo_env`."""
    path = Variable.get('REPO_ENV_PATH', default_var='/root/twt/.env')
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
    except Exception as e:
        LOG.warning('Could not read repo .env at %s: %s', path, e)

    context['ti'].xcom_push(key='repo_env', value=env)
    return env


def persist_post_run(**context):
    """After pipeline completes, record run metadata in Redis (best-effort)."""
    ti = context['ti']
    scheduled = ti.xcom_pull(task_ids='decide_window', key='scheduled_window')
    run_meta = {
        'dag_run_id': context.get('run_id'),
        'scheduled': scheduled,
        'timestamp': datetime.utcnow().isoformat()
    }
    r = get_redis_client()
    if r:
        try:
            r.lpush('scheduler:history', json.dumps(run_meta))
            # trim history
            r.ltrim('scheduler:history', 0, 999)
            # Mark window as successful if pipeline ran
            if scheduled and scheduled.get('status') == 'run' and 'window_key' in scheduled:
                r.set(scheduled['window_key'], 'success')
        except Exception:
            LOG.exception('Failed to persist post-run metadata')
    else:
        LOG.debug('Redis unavailable; skipping persist_post_run')
        # Fallback to Airflow Variable
        try:
            if scheduled and scheduled.get('status') == 'run' and 'window_key' in scheduled:
                Variable.set(scheduled['window_key'], 'success')
        except Exception:
            LOG.exception('Failed to persist window success to Airflow Variable')


with DAG(
    dag_id='scraper_humanized_scheduler',
    default_args=DEFAULT_ARGS,
    start_date=datetime(2025, 11, 1),
    schedule_interval='*/15 * * * *',
    catchup=False,
    max_active_runs=1,
    tags=['twt', 'mlops'],
) as dag:

    # First load repo .env into XCom so downstream tasks can access it
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

    # Ensure repo .env is loaded before decision logic runs
    load_env >> decide

    with TaskGroup('pipeline', tooltip='Run scraper->ingest->quality->trainer') as pipeline:

        # Try to import DockerOperator lazily. Some Airflow installs don't have the docker
        # provider available at DAG-parse time which causes the whole DAG file to break.
        try:
            from airflow.providers.docker.operators.docker import DockerOperator
        except Exception:
            DockerOperator = None
            LOG.warning('DockerOperator provider not available; using EmptyOperator placeholders')

        # NOTE: environment values below are Jinja-templated to pull from XCom set by decide_window
        # Map host .env path (optional) from Airflow Variable `REPO_ENV_PATH` into container at /app/.env
        repo_env_host = Variable.get('REPO_ENV_PATH', default_var='/root/twt/.env')
        host_env_mount = f"{repo_env_host}:/app/.env:ro"
        if DockerOperator:
            try:
                scraper = DockerOperator(
                task_id='scraper_task',
                image='twt-scraper:latest',
                api_version='auto',
                auto_remove=True,
                docker_url='unix://var/run/docker.sock',
                network_mode='twt_mlops-network',
                mount_tmp_dir=False,
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
                },
                mounts=[
                    {'source': '/root/twt/cookies.json', 'target': '/app/cookies.json', 'type': 'bind', 'read_only': True},
                    {'source': '/root/twt/data/raw', 'target': '/app/data/raw', 'type': 'bind'},
                ],
                # Resource limits for scraper (light)
                mem_limit='1g',
                cpus=0.5,
                command=None,
                )
            except Exception:
                LOG.exception('Failed to instantiate DockerOperator for scraper_task; falling back to EmptyOperator')
                scraper = EmptyOperator(task_id='scraper_task')
        else:
            scraper = EmptyOperator(task_id='scraper_task')

        if DockerOperator:
            try:
                ingest = DockerOperator(
                task_id='ingest_task',
                image='twt-ingest:latest',
                api_version='auto',
                auto_remove=True,
                docker_url='unix://var/run/docker.sock',
                network_mode='twt_mlops-network',
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
                },
                mounts=[
                    {'source': '/root/twt/data', 'target': '/app/data', 'type': 'bind'},
                ],
                mem_limit='1g',
                cpus=0.5,
            )
            except Exception:
                LOG.exception('Failed to instantiate DockerOperator for ingest_task; falling back to EmptyOperator')
                ingest = EmptyOperator(task_id='ingest_task')
        else:
            ingest = EmptyOperator(task_id='ingest_task')

        if DockerOperator:
            try:
                quality_gate = DockerOperator(
                task_id='quality_gate_task',
                image='twt-quality-gate:latest',
                api_version='auto',
                auto_remove=True,
                docker_url='unix://var/run/docker.sock',
                network_mode='twt_mlops-network',
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
                },
                mounts=[
                    {'source': '/root/twt/reports', 'target': '/app/reports', 'type': 'bind'},
                ],
                mem_limit='1g',
                cpus=0.5,
            )
            except Exception:
                LOG.exception('Failed to instantiate DockerOperator for quality_gate_task; falling back to EmptyOperator')
                quality_gate = EmptyOperator(task_id='quality_gate_task')
        else:
            quality_gate = EmptyOperator(task_id='quality_gate_task')

        if DockerOperator:
            try:
                trainer = DockerOperator(
                task_id='trainer_task',
                image='twt-trainer:latest',
                api_version='auto',
                auto_remove=True,
                docker_url='unix://var/run/docker.sock',
                network_mode='twt_mlops-network',
                environment={
                    'SERVICE_NAME': 'trainer',
                    'TRAINER_MODE': 'once',
                    'MLFLOW_TRACKING_URI': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['MLFLOW_TRACKING_URI'] }}",
                    'MLFLOW_S3_ENDPOINT_URL': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['MLFLOW_S3_ENDPOINT_URL'] }}",
                    'AWS_ACCESS_KEY_ID': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['MINIO_ACCESS_KEY'] }}",
                    'AWS_SECRET_ACCESS_KEY': "{{ ti.xcom_pull(task_ids='decide_window', key='scheduled_window')['env']['MINIO_SECRET_KEY'] }}",
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
                },
                mounts=[
                    {'source': '/root/twt/models', 'target': '/app/models', 'type': 'bind'},
                    {'source': '/root/twt/reports', 'target': '/app/reports', 'type': 'bind'},
                ],
                # Heavier resource limits for the trainer (cap to 1 CPU, 6GB RAM on 2-core/8GB VPS)
                mem_limit='6g',
                cpus=1.0,
            )
            except Exception:
                LOG.exception('Failed to instantiate DockerOperator for trainer_task; falling back to EmptyOperator')
                trainer = EmptyOperator(task_id='trainer_task')
        else:
            trainer = EmptyOperator(task_id='trainer_task')

        scraper >> ingest >> quality_gate >> trainer

    persist = PythonOperator(task_id='persist_post_run', python_callable=persist_post_run, provide_context=True)

    decide >> [pipeline, do_skip]
    pipeline >> persist
