#!/bin/bash
# Setup Airflow Variables for CI/CD Pipeline
# Run this script once to configure deployment automation

set -e

echo "Setting up Airflow variables for CI/CD pipeline..."

# Set MLflow experiment name
docker exec airflow-scheduler airflow variables set \
    mlflow_experiment_name "bertopic-pemerintah"

# Set minimum coherence score for deployment
docker exec airflow-scheduler airflow variables set \
    min_coherence_score "0.3"

echo "✓ Airflow variables configured"

# Enable DAGs
echo "Enabling deployment DAGs..."

docker exec airflow-scheduler airflow dags unpause model_deployment_pipeline || true
docker exec airflow-scheduler airflow dags unpause model_training_watcher || true

echo "✓ Deployment DAGs enabled"

# Check DAG status
echo ""
echo "DAG Status:"
docker exec airflow-scheduler airflow dags list | grep -E "model_deployment|model_training_watcher"

echo ""
echo "✅ CI/CD pipeline setup complete!"
echo ""
echo "Next steps:"
echo "1. Access Airflow UI: http://localhost:8080"
echo "2. Check DAGs: model_deployment_pipeline, model_training_watcher"
echo "3. Trigger a deployment: airflow dags trigger model_deployment_pipeline"
echo ""
echo "For more info, see CI_CD_DEPLOYMENT_GUIDE.md"
