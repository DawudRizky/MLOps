"""
BERTopic Trainer Service with Drift Detection
Trains topic models and tracks them in MLflow
"""
import asyncio
import json
import os
import pickle
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from bertopic import BERTopic
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import CountVectorizer
import mlflow

from common import (
    get_config,
    get_logger,
    setup_logging,
    metrics,
    MinIOClient,
    RedisCache,
    Database
)


class BERTopicTrainer:
    """Train and track BERTopic models with MLflow."""
    
    def __init__(self):
        """Initialize trainer."""
        self.config = get_config()
        self.logger = get_logger(__name__)
        
        # Initialize services
        self.storage = MinIOClient()
        self.cache = RedisCache()
        self.db = Database()
        
        # MLflow setup
        mlflow.set_tracking_uri(self.config.mlflow_tracking_uri)
        mlflow.set_experiment("bertopic-pemerintah")
        
        # Model config - Use environment variable or lightweight default
        self.embedding_model_name = os.getenv(
            "EMBEDDING_MODEL", 
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        self.min_topic_size = int(os.getenv("MIN_TOPIC_SIZE", "2"))  # Lowered from 10 for testing with small dataset
        self.nr_topics = "auto"
        self.embedding_batch_size = 8  # Reduced to 8 for memory efficiency on limited resources
        self.max_training_samples = int(os.getenv("MAX_TRAINING_SAMPLES", "1000"))  # Limit dataset size
        
        self.logger.info("Initialized BERTopic Trainer")
    
    def export_dataset_snapshot(self, df: pd.DataFrame, run_timestamp: str) -> Optional[str]:
        """
        Export training dataset to CSV for DVC versioning.
        
        Args:
            df: Training dataframe
            run_timestamp: Timestamp identifier for this run (e.g., '2025-12-18_morning')
            
        Returns:
            Path to exported CSV file or None if failed
        """
        try:
            # Create datasets directory if not exists
            datasets_dir = os.path.join('/app/data', 'datasets')
            os.makedirs(datasets_dir, exist_ok=True)
            
            # Generate filename with timestamp
            filename = f"tweets_{run_timestamp}.csv"
            filepath = os.path.join(datasets_dir, filename)
            
            # Export to CSV with metadata
            df_export = df.copy()
            df_export['export_timestamp'] = datetime.now().isoformat()
            df_export['dataset_version'] = run_timestamp
            
            df_export.to_csv(filepath, index=False, encoding='utf-8')
            
            file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
            self.logger.info(f"📊 Exported dataset snapshot: {filename} ({file_size_mb:.2f} MB, {len(df)} rows)")
            
            # Also save metadata JSON
            metadata = {
                'filename': filename,
                'timestamp': run_timestamp,
                'row_count': len(df),
                'file_size_mb': round(file_size_mb, 2),
                'columns': list(df.columns),
                'date_range': {
                    'oldest': df['created_at'].min().isoformat() if 'created_at' in df else None,
                    'newest': df['created_at'].max().isoformat() if 'created_at' in df else None,
                },
                'exported_at': datetime.now().isoformat()
            }
            
            metadata_path = filepath.replace('.csv', '.json')
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            return filepath
            
        except Exception as e:
            self.logger.error(f"Error exporting dataset snapshot: {e}")
            return None
    
    def cleanup_old_tweets(self, retention_days: int = 7) -> int:
        """
        Delete tweets older than retention_days to prevent data from piling up.
        
        Args:
            retention_days: Number of days to retain tweets (default: 7)
            
        Returns:
            Number of tweets deleted
        """
        try:
            cutoff_time = datetime.now() - timedelta(days=retention_days)
            
            # First count how many will be deleted
            count_query = "SELECT COUNT(*) FROM tweets WHERE created_at < %s"
            result = self.db.fetch_one(count_query, (cutoff_time,))
            count_to_delete = result[0] if result else 0
            
            if count_to_delete == 0:
                self.logger.info(f"No tweets older than {retention_days} days to delete")
                return 0
            
            # Delete old tweets
            delete_query = "DELETE FROM tweets WHERE created_at < %s"
            success = self.db.execute(delete_query, (cutoff_time,))
            
            if success:
                self.logger.info(f"🗑️ Deleted {count_to_delete} tweets older than {retention_days} days (before {cutoff_time.isoformat()})")
                metrics.counter('tweets_deleted', count_to_delete, {'retention_days': retention_days})
                return count_to_delete
            else:
                self.logger.error("Failed to delete old tweets")
                return 0
                
        except Exception as e:
            self.logger.error(f"Error cleaning up old tweets: {e}")
            metrics.record_error('tweet_cleanup', str(e))
            return 0
    
    def get_training_data(self, hours: int = 168) -> Optional[pd.DataFrame]:
        """
        Get training data from database.
        
        Args:
            hours: Number of hours of data to fetch (default: 7 days)
        """
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            query = """
                SELECT 
                    tweet_id,
                    text,
                    created_at,
                    user_id,
                    like_count,
                    retweet_count,
                    engagement_rate,
                    lang
                FROM tweets
                WHERE processed_at > %s
                    AND char_count >= 20
                    AND lang IN ('id', 'in', 'en')
                ORDER BY created_at DESC
                LIMIT %s
            """
            
            rows = self.db.fetch_dict(query, (cutoff_time, self.max_training_samples))
            
            if not rows:
                self.logger.warning("No training data available")
                return None
            
            df = pd.DataFrame(rows)
            self.logger.info(f"Loaded {len(df)} tweets for training")
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error getting training data: {e}")
            return None
    
    def prepare_data(self, df: pd.DataFrame) -> List[str]:
        """Prepare texts for training."""
        # Remove very short texts
        df = df[df['text'].str.len() >= 20].copy()
        
        # Clean texts
        texts = df['text'].tolist()
        
        self.logger.info(f"Prepared {len(texts)} texts for training")
        return texts
    
    def train_model(self, texts: List[str]) -> Optional[BERTopic]:
        """Train BERTopic model."""
        try:
            self.logger.info("Training BERTopic model...")
            
            # Initialize embedding model with batch size for memory efficiency
            embedding_model = SentenceTransformer(self.embedding_model_name)
            
            # Pre-compute embeddings in smaller batches to control memory
            self.logger.info(f"Computing embeddings with batch size {self.embedding_batch_size}...")
            embeddings = embedding_model.encode(
                texts, 
                batch_size=self.embedding_batch_size,
                show_progress_bar=True,
                convert_to_numpy=True
            )
            self.logger.info(f"Computed embeddings for {len(embeddings)} documents")
            
            # Custom vectorizer for Indonesian/English
            vectorizer_model = CountVectorizer(
                ngram_range=(1, 2),
                stop_words=None,  # Keep all words for multilingual
                min_df=2
            )
            
            # Initialize BERTopic with pre-computed embeddings
            topic_model = BERTopic(
                embedding_model=embedding_model,
                vectorizer_model=vectorizer_model,
                min_topic_size=self.min_topic_size,
                nr_topics=self.nr_topics,
                calculate_probabilities=False,  # Disable to save memory
                verbose=True
            )
            
            # Fit model with pre-computed embeddings
            topics, _ = topic_model.fit_transform(texts, embeddings)
            
            self.logger.info(f"Training complete. Found {len(set(topics))} topics")
            
            return topic_model
            
        except Exception as e:
            self.logger.error(f"Error training model: {e}")
            return None
    
    def evaluate_model(self, topic_model: BERTopic, texts: List[str]) -> Dict[str, Any]:
        """Evaluate model quality."""
        try:
            # Get topic info
            topic_info = topic_model.get_topic_info()
            
            # Calculate metrics
            num_topics = len(topic_info) - 1  # Exclude outlier topic (-1)
            avg_topic_size = topic_info['Count'].mean()
            
            # Topic coherence (simplified)
            topics_dict = {topic: topic_model.get_topic(topic) for topic in range(num_topics)}
            
            # Distribution metrics
            topics_pred, _ = topic_model.transform(texts)
            
            # Convert to numpy array if needed
            if not isinstance(topics_pred, (list, np.ndarray)):
                topics_pred = np.array([topics_pred])
            else:
                topics_pred = np.array(topics_pred)
            
            topic_counts = pd.Series(topics_pred).value_counts()
            
            # Gini coefficient for topic distribution balance
            topic_sizes = topic_counts.values
            topic_sizes_sorted = np.sort(topic_sizes)
            n = len(topic_sizes_sorted)
            index = np.arange(1, n + 1)
            gini = (2 * np.sum(index * topic_sizes_sorted)) / (n * np.sum(topic_sizes_sorted)) - (n + 1) / n
            
            # Calculate outliers ratio safely
            outliers_count = np.sum(topics_pred == -1)
            outliers_ratio = float(outliers_count / len(topics_pred)) if len(topics_pred) > 0 else 0.0
            
            metrics_data = {
                'num_topics': num_topics,
                'avg_topic_size': float(avg_topic_size),
                'total_documents': len(texts),
                'outliers_ratio': outliers_ratio,
                'topic_balance_gini': float(gini),  # 0 = perfect balance, 1 = all in one topic
            }
            
            self.logger.info(f"Model evaluation: {metrics_data}")
            
            return metrics_data
            
        except Exception as e:
            self.logger.error(f"Error evaluating model: {e}")
            return {}
    
    def detect_topic_drift(self, current_topics: Dict[int, List[tuple]], previous_run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Detect topic drift compared to previous model.
        
        Returns drift metrics and whether significant drift detected.
        """
        try:
            if not previous_run_id:
                self.logger.info("No previous model for drift detection")
                return {'drift_detected': False, 'message': 'No baseline model'}
            
            # Load previous topics from cache
            previous_topics = self.cache.get_json(f'topics_{previous_run_id}')
            
            if not previous_topics:
                self.logger.warning("Could not load previous topics")
                return {'drift_detected': False, 'message': 'Previous topics not available'}
            
            # Calculate topic similarity (simplified - compare top words)
            def get_top_words(topic_list, n=10):
                return set([word for word, _ in topic_list[:n]])
            
            # Compare topics
            similarities = []
            for topic_id, words in current_topics.items():
                if topic_id == -1:  # Skip outliers
                    continue
                
                current_words = get_top_words(words)
                
                # Find most similar previous topic
                max_similarity = 0
                for prev_id, prev_words in previous_topics.items():
                    if int(prev_id) == -1:
                        continue
                    
                    prev_words_set = set([w for w, _ in prev_words[:10]])
                    similarity = len(current_words & prev_words_set) / len(current_words | prev_words_set)
                    max_similarity = max(max_similarity, similarity)
                
                similarities.append(max_similarity)
            
            avg_similarity = np.mean(similarities) if similarities else 0
            drift_score = 1 - avg_similarity  # 0 = no drift, 1 = complete drift
            
            # Threshold for significant drift
            drift_detected = drift_score > 0.5
            
            drift_info = {
                'drift_detected': drift_detected,
                'drift_score': float(drift_score),
                'avg_topic_similarity': float(avg_similarity),
                'compared_to_run': previous_run_id,
                'message': f"{'Significant' if drift_detected else 'Minor'} drift detected (score: {drift_score:.3f})"
            }
            
            self.logger.info(drift_info['message'])
            
            return drift_info
            
        except Exception as e:
            self.logger.error(f"Error detecting drift: {e}")
            return {'drift_detected': False, 'error': str(e)}
    
    def save_model(self, topic_model: BERTopic, run_id: str) -> bool:
        """Save model to MinIO (backup storage)."""
        try:
            # Serialize model
            model_bytes = pickle.dumps(topic_model)
            
            # Save to MinIO using configured bucket
            object_name = f"bertopic_{run_id}.pkl"
            self.storage.upload_data(
                bucket_name=self.config.bucket_models,  # Use config bucket
                object_name=f"models/{object_name}",
                data=model_bytes,
                content_type='application/octet-stream'
            )
            
            self.logger.info(f"Saved model to MinIO: {self.config.bucket_models}/models/{object_name}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving model: {e}")
            return False
    
    def log_to_mlflow(self, topic_model: BERTopic, texts: List[str], eval_metrics: Dict[str, Any], drift_info: Dict[str, Any], dataset_version: str = None, dataset_path: str = None) -> str:
        """Log model and metrics to MLflow."""
        try:
            with mlflow.start_run() as run:
                # Log parameters
                mlflow.log_param("embedding_model", self.embedding_model_name)
                mlflow.log_param("min_topic_size", self.min_topic_size)
                mlflow.log_param("num_documents", len(texts))
                mlflow.log_param("nr_topics", self.nr_topics)
                
                # Log dataset version for DVC tracking
                if dataset_version:
                    mlflow.log_param("dataset_version", dataset_version)
                    mlflow.set_tag("dataset_version", dataset_version)
                
                # Log metrics
                mlflow.log_metrics(eval_metrics)
                mlflow.log_metrics({
                    'drift_score': drift_info.get('drift_score', 0),
                    'drift_detected': 1 if drift_info.get('drift_detected') else 0,
                })
                
                # Log dataset using MLflow Dataset tracking
                if dataset_path and os.path.exists(dataset_path):
                    # Create MLflow dataset object
                    try:
                        from mlflow.data.pandas_dataset import PandasDataset
                        df = pd.read_csv(dataset_path)
                        dataset = mlflow.data.from_pandas(
                            df,
                            source=dataset_path,
                            name=f"tweets_{dataset_version}",
                            targets="text"  # The text column is our target for training
                        )
                        mlflow.log_input(dataset, context="training")
                        self.logger.info(f"📊 Logged dataset to MLflow: {dataset_version}")
                    except Exception as e:
                        self.logger.warning(f"Failed to log dataset object, using artifact: {e}")
                        mlflow.log_artifact(dataset_path, artifact_path="dataset")
                    
                    # Also log metadata
                    metadata_path = dataset_path.replace('.csv', '.json')
                    if os.path.exists(metadata_path):
                        mlflow.log_artifact(metadata_path, artifact_path="dataset")
                    self.logger.info(f"📎 Logged dataset snapshot to MLflow: {dataset_version}")
                
                # Log topic info as artifact
                topic_info = topic_model.get_topic_info()
                topic_info_path = f"/tmp/topic_info_{run.info.run_id}.csv"
                topic_info.to_csv(topic_info_path, index=False)
                mlflow.log_artifact(topic_info_path)
                
                # Log top topics
                for topic_id in range(min(10, eval_metrics['num_topics'])):
                    topic_words = topic_model.get_topic(topic_id)
                    if topic_words:
                        top_words = [word for word, _ in topic_words[:10]]
                        mlflow.log_text(
                            ', '.join(top_words),
                            f"topics/topic_{topic_id}_words.txt"
                        )
                
                # Log the model itself as a pickle artifact to MLflow
                model_path = f"/tmp/bertopic_model_{run.info.run_id}.pkl"
                with open(model_path, 'wb') as f:
                    pickle.dump(topic_model, f)
                
                # Create model signature with input/output schema
                from mlflow.models.signature import infer_signature
                
                # Sample input/output for signature
                sample_texts = texts[:5] if len(texts) >= 5 else texts
                sample_input = pd.DataFrame({"text": sample_texts})
                
                try:
                    # Get sample predictions
                    topics, _ = topic_model.transform(sample_texts)
                    sample_output = pd.DataFrame({"topic": topics})
                    signature = infer_signature(sample_input, sample_output)
                except Exception as e:
                    self.logger.warning(f"Could not infer signature: {e}")
                    signature = None
                
                # Create input example
                input_example = sample_input.head(1)
                
                # Log model artifact with signature
                mlflow.log_artifact(model_path, artifact_path="model")
                self.logger.info("Logged model artifact to MLflow")
                
                # Register model in MLflow Model Registry with metadata
                model_name = "bertopic-pemerintah-model"
                try:
                    # Log as pyfunc with signature and input example
                    mlflow.pyfunc.log_model(
                        artifact_path="registered_model",
                        python_model=None,
                        artifacts={"model_file": model_path},
                        registered_model_name=model_name,
                        signature=signature,
                        input_example=input_example,
                        code_path=None,
                        pip_requirements=[
                            f"bertopic=={topic_model.__version__ if hasattr(topic_model, '__version__') else '0.15.0'}",
                            "sentence-transformers",
                            "scikit-learn"
                        ]
                    )
                    self.logger.info(f"✅ Registered model in MLflow Model Registry: {model_name}")
                except Exception as e:
                    # Fallback: register the artifact path
                    self.logger.warning(f"pyfunc registration failed, using register_model: {e}")
                    model_uri = f"runs:/{run.info.run_id}/model"
                    mlflow.register_model(model_uri=model_uri, name=model_name)
                    self.logger.info(f"✅ Registered model via register_model: {model_name}")
                
                # Tag run
                mlflow.set_tag("model_type", "bertopic")
                mlflow.set_tag("drift_detected", drift_info.get('drift_detected', False))
                mlflow.set_tag("registered_model_name", model_name)
                
                run_id = run.info.run_id
                self.logger.info(f"Logged to MLflow: run_id={run_id}")
                
                return run_id
                
        except Exception as e:
            self.logger.error(f"Error logging to MLflow: {e}")
            return ""
    
    async def train(self) -> Optional[str]:
        """Run complete training pipeline."""
        try:
            self.logger.info("="*50)
            self.logger.info("Starting BERTopic training")
            self.logger.info("="*50)
            
            # Clean up old tweets (keep only last 7 days)
            retention_days = int(os.getenv("TWEET_RETENTION_DAYS", "7"))
            deleted_count = self.cleanup_old_tweets(retention_days=retention_days)
            if deleted_count > 0:
                self.logger.info(f"Cleanup: Removed {deleted_count} tweets older than {retention_days} days")
            
            # Check quality gate
            quality_check = self.cache.get_json('latest_quality_check')
            if quality_check and not quality_check.get('overall_passed'):
                self.logger.warning("Quality gate failed. Skipping training.")
                self.logger.warning(f"Quality score: {quality_check.get('quality_score', 0):.3f}")
                return None
            
            # Get training data
            df = self.get_training_data(hours=168)  # Last 7 days
            if df is None or len(df) < 10:  # Lowered from 100 for testing
                self.logger.warning(f"Insufficient training data: {len(df) if df is not None else 0} tweets")
                return None
            
            # Export dataset snapshot for DVC versioning
            run_timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            window_name = os.getenv('WINDOW_NAME', 'manual')
            dataset_version = f"{run_timestamp}_{window_name}"
            dataset_path = self.export_dataset_snapshot(df, dataset_version)
            
            # Prepare texts
            texts = self.prepare_data(df)
            if len(texts) < 10:  # Lowered from 100 for testing
                self.logger.warning(f"Too few texts after preparation: {len(texts)}")
                return None
            
            # Train model
            topic_model = self.train_model(texts)
            if topic_model is None:
                return None
            
            # Evaluate model
            eval_metrics = self.evaluate_model(topic_model, texts)
            
            # Get previous run for drift detection
            previous_run_id = self.cache.get('latest_model_run_id')
            
            # Detect drift
            current_topics = {i: topic_model.get_topic(i) for i in range(eval_metrics['num_topics'])}
            drift_info = self.detect_topic_drift(current_topics, previous_run_id)
            
            # Log to MLflow with dataset version
            run_id = self.log_to_mlflow(topic_model, texts, eval_metrics, drift_info, 
                                       dataset_version=dataset_version, dataset_path=dataset_path)
            
            if run_id:
                # Model is stored via MLflow artifacts/registry; no separate backup upload
                # Cache current topics and run ID
                topics_dict = {topic: topic_model.get_topic(topic) for topic in range(eval_metrics['num_topics'])}
                self.cache.set_json(f'topics_{run_id}', topics_dict, ttl=timedelta(days=7))
                self.cache.set('latest_model_run_id', run_id, ttl=timedelta(days=7))
                
                self.logger.info("="*50)
                self.logger.info(f"Training complete: run_id={run_id}")
                self.logger.info(f"Topics: {eval_metrics['num_topics']}")
                self.logger.info(f"Drift score: {drift_info.get('drift_score', 0):.3f}")
                self.logger.info("="*50)
                
                return run_id
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error in training pipeline: {e}")
            return None
    
    async def run_scheduled(self, interval_hours: int = 24) -> None:
        """Run training on schedule."""
        self.logger.info(f"Starting scheduled training (interval: {interval_hours}h)")
        
        while True:
            try:
                # Run training
                run_id = await self.train()
                
                if run_id:
                    self.logger.info(f"Training successful: {run_id}")
                else:
                    self.logger.warning("Training failed or skipped")
                
                # Wait before next training
                wait_seconds = interval_hours * 3600
                self.logger.info(f"Next training in {interval_hours} hours")
                await asyncio.sleep(wait_seconds)
                
            except KeyboardInterrupt:
                self.logger.info("Trainer stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Error in training loop: {e}")
                await asyncio.sleep(3600)  # Wait 1 hour on error


async def main():
    """Main entry point."""
    setup_logging()
    logger = get_logger(__name__)
    
    logger.info("Starting BERTopic Trainer Service")
    
    trainer = BERTopicTrainer()
    
    # Check for once mode (train once then exit)
    trainer_mode = os.getenv('TRAINER_MODE', 'continuous')
    
    if trainer_mode == 'once':
        logger.info("🎯 ONCE MODE - Training once then exiting")
        
        try:
            # Run training
            result = await trainer.train()
            
            # Log final result
            if result.get('success'):
                logger.info(f"✅ Training complete - Model: {result.get('model_name')}, Version: {result.get('version')}")
            else:
                logger.warning(f"❌ Training failed - {result.get('error', 'Unknown error')}")
            
        except Exception as e:
            logger.error(f"Error in once mode: {e}")
        
        logger.info("Trainer shutdown complete (once mode)")
        return
    
    # Continuous mode
    try:
        # Run once immediately, then schedule
        await trainer.train()
        
        # Continue with scheduled runs
        await trainer.run_scheduled(interval_hours=24)
    except KeyboardInterrupt:
        logger.info("Trainer stopped")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        logger.info("Trainer shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
