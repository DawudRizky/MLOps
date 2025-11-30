from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

# Definisi DAG
with DAG(
    dag_id="hello_flow",
    description="Contoh DAG sederhana",
    schedule_interval=timedelta(days=1),
    start_date=datetime(2025, 11, 10),
    catchup=False,
    tags=["contoh"],
) as dag:

    # Task 1
    hello = BashOperator(
        task_id="say_hello",
        bash_command="echo 'Halo dari Airflow!'"
    )

    # Task 2
    date = BashOperator(
        task_id="show_date",
        bash_command="date"
    )

    # Urutan eksekusi
    hello >> date
