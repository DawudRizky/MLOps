"""
Configuration management for all services.
"""
import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    """Application configuration with environment variable support."""
    
    # Service Info
    service_name: str = Field(default="mlops-service", env="SERVICE_NAME")
    environment: str = Field(default="development", env="ENVIRONMENT")
    debug: bool = Field(default=False, env="DEBUG")
    
    # API Settings
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=8000, env="API_PORT")
    
    # MinIO/S3 Settings
    minio_endpoint: str = Field(default="minio:9000", env="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="minioadmin", env="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="minioadmin123", env="MINIO_SECRET_KEY")
    minio_secure: bool = Field(default=False, env="MINIO_SECURE")
    
    # S3 Buckets (MinIO)
    bucket_data: str = Field(default="mlops-data", env="BUCKET_DATA")
    bucket_models: str = Field(default="mlops-models", env="BUCKET_MODELS")
    
    # PostgreSQL Settings
    postgres_host: str = Field(default="postgres", env="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, env="POSTGRES_PORT")
    postgres_user: str = Field(default="mlflow", env="POSTGRES_USER")
    postgres_password: str = Field(default="mlflow123", env="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="mlflow", env="POSTGRES_DB")
    
    # Redis Settings
    redis_host: str = Field(default="redis", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_db: int = Field(default=0, env="REDIS_DB")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    
    # MLflow Settings
    mlflow_tracking_uri: str = Field(default="http://mlflow:5000", env="MLFLOW_TRACKING_URI")
    mlflow_experiment_name: str = Field(default="pemerintah-topic-modeling", env="MLFLOW_EXPERIMENT_NAME")
    
    # Model Settings
    model_name: str = Field(default="bertopic-pemerintah", env="MODEL_NAME")
    embedding_model: str = Field(default="indobenchmark/indobert-base-p1", env="EMBEDDING_MODEL")
    min_topic_size: int = Field(default=10, env="MIN_TOPIC_SIZE")
    nr_topics: Optional[int] = Field(default=None, env="NR_TOPICS")
    
    # Drift Detection
    drift_threshold: float = Field(default=0.1, env="DRIFT_THRESHOLD")
    drift_check_interval: int = Field(default=24, env="DRIFT_CHECK_INTERVAL")  # hours
    
    # Twitter Scraper Settings
    twitter_cookies_file: str = Field(default="cookies.json", env="TWITTER_COOKIES_FILE")
    twitter_search_query: str = Field(default="pemerintah", env="TWITTER_SEARCH_QUERY")
    twitter_search_type: str = Field(default="Latest", env="TWITTER_SEARCH_TYPE")
    twitter_max_tweets: int = Field(default=1000, env="TWITTER_MAX_TWEETS")
    twitter_exclude_retweets: bool = Field(default=True, env="TWITTER_EXCLUDE_RETWEETS")
    twitter_exclude_replies: bool = Field(default=True, env="TWITTER_EXCLUDE_REPLIES")
    
    # ML Settings
    ml_target_language: str = Field(default="id,en", env="ML_TARGET_LANGUAGE")
    ml_min_text_length: int = Field(default=20, env="ML_MIN_TEXT_LENGTH")
    
    # Quality Gate Settings
    min_confidence: float = Field(default=0.7, env="MIN_CONFIDENCE")
    max_outlier_ratio: float = Field(default=0.3, env="MAX_OUTLIER_RATIO")
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_format: str = Field(default="json", env="LOG_FORMAT")
    
    @property
    def postgres_url(self) -> str:
        """Get PostgreSQL connection URL."""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    @property
    def redis_url(self) -> str:
        """Get Redis connection URL."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get or create the global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config
