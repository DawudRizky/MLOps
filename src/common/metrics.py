"""
Prometheus metrics collection for all services.
"""
from prometheus_client import Counter, Gauge, Histogram, generate_latest
from typing import Dict, Any
from .config import get_config


class MetricsCollector:
    """Centralized metrics collection for MLOps services."""
    
    def __init__(self):
        """Initialize metrics collectors."""
        config = get_config()
        # Replace hyphens with underscores for Prometheus metric names
        service = config.service_name.replace('-', '_')
        
        # Request metrics
        self.requests_total = Counter(
            f'{service}_requests_total',
            'Total number of requests',
            ['method', 'endpoint', 'status']
        )
        
        self.request_duration = Histogram(
            f'{service}_request_duration_seconds',
            'Request duration in seconds',
            ['method', 'endpoint']
        )
        
        # Processing metrics
        self.items_processed = Counter(
            f'{service}_items_processed_total',
            'Total number of items processed',
            ['item_type', 'status']
        )
        
        self.processing_duration = Histogram(
            f'{service}_processing_duration_seconds',
            'Processing duration in seconds',
            ['operation']
        )
        
        # Model metrics
        self.model_predictions = Counter(
            f'{service}_model_predictions_total',
            'Total number of model predictions',
            ['model_name', 'status']
        )
        
        self.model_confidence = Histogram(
            f'{service}_model_confidence',
            'Model prediction confidence scores',
            ['model_name']
        )
        
        self.model_drift_score = Gauge(
            f'{service}_model_drift_score',
            'Current model drift score',
            ['model_name']
        )
        
        # Topic modeling metrics
        self.topics_discovered = Gauge(
            f'{service}_topics_discovered',
            'Number of topics discovered',
            ['model_version']
        )
        
        self.topic_coherence = Gauge(
            f'{service}_topic_coherence_score',
            'Topic coherence score',
            ['model_version']
        )
        
        # Data metrics
        self.tweets_collected = Counter(
            f'{service}_tweets_collected_total',
            'Total tweets collected',
            ['source']
        )
        
        self.tweets_processed = Counter(
            f'{service}_tweets_processed_total',
            'Total tweets processed',
            ['status']
        )
        
        # Quality metrics
        self.quality_checks_total = Counter(
            f'{service}_quality_checks_total',
            'Total quality checks performed',
            ['check_type', 'result']
        )
        
        self.quality_score = Gauge(
            f'{service}_quality_score',
            'Current data quality score',
            ['dataset']
        )
        
        # Storage metrics
        self.storage_operations = Counter(
            f'{service}_storage_operations_total',
            'Total storage operations',
            ['operation', 'bucket', 'status']
        )
        
        self.storage_size_bytes = Gauge(
            f'{service}_storage_size_bytes',
            'Current storage size in bytes',
            ['bucket']
        )
        
        # Error metrics
        self.errors_total = Counter(
            f'{service}_errors_total',
            'Total number of errors',
            ['error_type', 'operation']
        )
    
    def record_request(self, method: str, endpoint: str, status: int, duration: float):
        """Record HTTP request metrics."""
        self.requests_total.labels(method=method, endpoint=endpoint, status=str(status)).inc()
        self.request_duration.labels(method=method, endpoint=endpoint).observe(duration)
    
    def record_processing(self, item_type: str, status: str, duration: float, operation: str = "default"):
        """Record item processing metrics."""
        self.items_processed.labels(item_type=item_type, status=status).inc()
        self.processing_duration.labels(operation=operation).observe(duration)
    
    def record_prediction(self, model_name: str, status: str, confidence: float):
        """Record model prediction metrics."""
        self.model_predictions.labels(model_name=model_name, status=status).inc()
        self.model_confidence.labels(model_name=model_name).observe(confidence)
    
    def update_drift_score(self, model_name: str, score: float):
        """Update model drift score."""
        self.model_drift_score.labels(model_name=model_name).set(score)
    
    def update_topics(self, model_version: str, num_topics: int, coherence: float):
        """Update topic modeling metrics."""
        self.topics_discovered.labels(model_version=model_version).set(num_topics)
        self.topic_coherence.labels(model_version=model_version).set(coherence)
    
    def record_tweet_collected(self, source: str = "api"):
        """Record tweet collection."""
        self.tweets_collected.labels(source=source).inc()
    
    def record_tweet_processed(self, status: str):
        """Record tweet processing."""
        self.tweets_processed.labels(status=status).inc()
    
    def record_quality_check(self, check_type: str, result: str):
        """Record quality check result."""
        self.quality_checks_total.labels(check_type=check_type, result=result).inc()
    
    def update_quality_score(self, dataset: str, score: float):
        """Update quality score."""
        self.quality_score.labels(dataset=dataset).set(score)
    
    def record_storage_operation(self, operation: str, bucket: str, status: str):
        """Record storage operation."""
        self.storage_operations.labels(operation=operation, bucket=bucket, status=status).inc()
    
    def update_storage_size(self, bucket: str, size_bytes: int):
        """Update storage size."""
        self.storage_size_bytes.labels(bucket=bucket).set(size_bytes)
    
    def record_error(self, error_type: str, operation: str):
        """Record error occurrence."""
        self.errors_total.labels(error_type=error_type, operation=operation).inc()
    
    def get_metrics(self) -> bytes:
        """Get current metrics in Prometheus format."""
        return generate_latest()


# Global metrics instance
metrics = MetricsCollector()
