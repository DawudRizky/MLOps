from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount
from datetime import datetime, timedelta

default_args = {
    'owner': 'airflow',
    'retries': 0,  # Tidak retry jika gagal
    'retry_delay': timedelta(minutes=10),
}

with DAG(
    dag_id='scraper_pipeline_v2',
    default_args=default_args,
    description='Cascade pipeline: scraper → ingest → quality → trainer',
    start_date=datetime(2025, 11, 10),
    schedule_interval='0 */12 * * *',  # setiap 12 jam sekali
    catchup=False,
    tags=['twt', 'mlops'],
) as dag:

    # ===================================================================
    # STEP 1: SCRAPER
    # ===================================================================
    scraper = DockerOperator(
        task_id='scraper_task',
        image='twt-scraper:latest',
        api_version='auto',
        auto_remove=True,
        docker_url='unix://var/run/docker.sock',
        network_mode='twt_mlops-network',
        mem_limit='4g',
        cpus=1.0,
        environment={
            'SERVICE_NAME': 'scraper',
            'TWITTER_COOKIES_FILE': '/app/cookies.json',
            'TWITTER_SEARCH_QUERY': '#petani OR pertanian OR hortikultura',
            'TWITTER_MAX_TWEETS': '40',
            'TWITTER_EXCLUDE_RETWEETS': 'true',
            'TWITTER_EXCLUDE_REPLIES': 'true',
            'SCRAPER_MODE': 'burst',
            'SCRAPER_DURATION': '600',
            'MINIO_ENDPOINT': 'minio:9000',
            'MINIO_ACCESS_KEY': 'minioadmin',
            'MINIO_SECRET_KEY': 'minioadmin123',
            'REDIS_HOST': 'redis',
            'POSTGRES_HOST': 'postgres',
            'POSTGRES_DB': 'mlflow',
            'POSTGRES_USER': 'mlflow',
            'POSTGRES_PASSWORD': 'mlflow123',
            'LOG_LEVEL': 'INFO',
        },
        mounts=[
            Mount(source='/root/twt/cookies.json', target='/app/cookies.json', type='bind', read_only=True),
            Mount(source='/root/twt/data/raw', target='/app/data/raw', type='bind'),
        ],
    )

    # ===================================================================
    # STEP 2: INGEST
    # ===================================================================
    ingest = DockerOperator(
        task_id='ingest_task',
        image='twt-ingest:latest',
        api_version='auto',
        auto_remove=True,
        docker_url='unix://var/run/docker.sock',
        network_mode='twt_mlops-network',
        mem_limit='4g',
        cpus=1.0,
        environment={
            'SERVICE_NAME': 'ingest',
            'INGEST_MODE': 'once',
            'MINIO_ENDPOINT': 'minio:9000',
            'REDIS_HOST': 'redis',
            'POSTGRES_HOST': 'postgres',
            'POSTGRES_DB': 'mlflow',
            'POSTGRES_USER': 'mlflow',
            'POSTGRES_PASSWORD': 'mlflow123',
        },
        mounts=[
            Mount(source='/root/twt/data/raw', target='/app/data/raw', type='bind'),
        ],
    )

    # ===================================================================
    # STEP 3: QUALITY GATE
    # ===================================================================
    quality_gate = DockerOperator(
        task_id='quality_gate_task',
        image='twt-quality-gate:latest',
        api_version='auto',
        auto_remove=True,
        docker_url='unix://var/run/docker.sock',
        network_mode='twt_mlops-network',
        mem_limit='4g',
        cpus=1.0,
        environment={
            'SERVICE_NAME': 'quality-gate',
            'QUALITY_MODE': 'once',
            'MINIO_ENDPOINT': 'minio:9000',
            'REDIS_HOST': 'redis',
            'POSTGRES_HOST': 'postgres',
            'POSTGRES_DB': 'mlflow',
            'POSTGRES_USER': 'mlflow',
            'POSTGRES_PASSWORD': 'mlflow123',
        },
    )

    # ===================================================================
    # STEP 4: TRAINER
    # ===================================================================
    trainer = DockerOperator(
        task_id='trainer_task',
        image='twt-trainer:latest',
        api_version='auto',
        auto_remove=True,
        docker_url='unix://var/run/docker.sock',
        network_mode='twt_mlops-network',
        mount_tmp_dir=False,
        mem_limit='4g',
        cpus=1.0,
        environment={
            'SERVICE_NAME': 'trainer',
            'TRAINER_MODE': 'once',
            'MLFLOW_TRACKING_URI': 'http://mlflow:5000',
            'AWS_ACCESS_KEY_ID': 'minioadmin',
            'AWS_SECRET_ACCESS_KEY': 'minioadmin123',
            'MLFLOW_S3_ENDPOINT_URL': 'http://minio:9000',
        },
    )

    # ===================================================================
    # SET DEPENDENCIES
    # ===================================================================
    scraper >> ingest >> quality_gate >> trainer
