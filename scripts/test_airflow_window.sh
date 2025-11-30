#!/bin/bash
# Test Airflow DAG window enforcement logic
# Usage: bash test_airflow_window.sh

set -e

AIRFLOW_WORKER=airflow-airflow-worker-1
DAG_ID=scraper_humanized_scheduler

echo "Triggering DAG: $DAG_ID"
TRIGGER_OUT=$(docker exec $AIRFLOW_WORKER airflow dags trigger $DAG_ID)
echo "$TRIGGER_OUT"

# Try to parse run_id from output
RUN_ID=$(echo "$TRIGGER_OUT" | grep -oE 'manual__[0-9T:+-]+' | head -n1)

if [ -z "$RUN_ID" ]; then
  echo "Could not parse run_id from trigger output. Trying to get latest run_id from list-runs."
  LIST_RUNS_OUT=$(docker exec $AIRFLOW_WORKER airflow dags list-runs -d $DAG_ID)
  echo "$LIST_RUNS_OUT"
  # Extract run_id from the second column, skipping header
  RUN_ID=$(echo "$LIST_RUNS_OUT" | awk 'NR>2 {print $3}' | tail -n 1)
fi

echo "Using run_id: $RUN_ID"

if [ -z "$RUN_ID" ]; then
  echo "Failed to get run_id. Exiting."
  exit 1
fi

# Wait for DAG run to start (poll every 5s, max 60s)
for i in {1..12}; do
  STATUS=$(docker exec $AIRFLOW_WORKER airflow dags list-runs -d $DAG_ID | grep "$RUN_ID" | awk '{print $12}')
  if [[ "$STATUS" == "running" || "$STATUS" == "success" || "$STATUS" == "failed" ]]; then
    break
  fi
  sleep 5
done

LOG_PATH="/opt/airflow/logs/dag_id=${DAG_ID}/run_id=${RUN_ID}/task_id=decide_window/attempt=1.log"
echo "Waiting for decide_window log file: $LOG_PATH"

for i in {1..12}; do
  if docker exec $AIRFLOW_WORKER test -f "$LOG_PATH"; then
    echo "Log file found. Printing contents:"
    docker exec $AIRFLOW_WORKER cat "$LOG_PATH"
    exit 0
  fi
  sleep 5
done

echo "Log file not found after waiting. The task may not have started yet or may have failed to create logs."
exit 2
