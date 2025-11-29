"""
Data Ingest Processor Service
Reads raw tweets from MinIO, validates, cleans, and stores in PostgreSQL
"""
import json
import asyncio
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
import re

from common import (
    get_config,
    get_logger,
    setup_logging,
    metrics,
    MinIOClient,
    RedisCache,
    Database
)


class DataIngestProcessor:
    """Process raw tweets and store in PostgreSQL."""
    
    def __init__(self):
        """Initialize ingest processor."""
        self.config = get_config()
        self.logger = get_logger(__name__)
        
        # Initialize services
        self.storage = MinIOClient()
        self.cache = RedisCache()
        self.db = Database()
        
        # Statistics
        self.processed_count = 0
        self.invalid_count = 0
        self.stored_count = 0
        
        self.logger.info("Initialized Data Ingest Processor")
    
    def validate_tweet(self, tweet: Dict[str, Any]):
        """
        Validate tweet data quality.
        
        Returns:
            (is_valid, error_message)
        """
        # Required fields
        required_fields = ['tweet_id', 'text', 'created_at', 'user_id']
        for field in required_fields:
            if field not in tweet or not tweet[field]:
                return False, f"Missing required field: {field}"
        
        # Text length validation
        text = tweet.get('text', '')
        if len(text) < 10:
            return False, "Text too short (< 10 characters)"
        
        if len(text) > 5000:
            return False, "Text too long (> 5000 characters)"
        
        # Language validation (if specified) - accept both 'id' and 'in' for Indonesian
        valid_languages = self.config.ml_target_language.split(',')
        # Add 'in' as alternative for 'id' (Indonesian)
        if 'id' in valid_languages and 'in' not in valid_languages:
            valid_languages.append('in')
        if tweet.get('lang') and tweet['lang'] not in valid_languages:
            return False, f"Invalid language: {tweet['lang']} (expected: {valid_languages})"
        
        # User validation
        user_followers = tweet.get('user_followers', 0)
        if user_followers < 0:
            return False, "Invalid follower count"
        
        # Engagement validation
        if any(tweet.get(field, 0) < 0 for field in ['retweet_count', 'like_count', 'reply_count']):
            return False, "Invalid engagement metrics"
        
        return True, None
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize tweet text."""
        if not text:
            return ""
        
        # Remove HTML entities
        import html
        text = html.unescape(text)
        
        # Remove zero-width characters
        text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        # Remove excessive punctuation
        text = re.sub(r'([!?.]){4,}', r'\1\1\1', text)
        
        return text.strip()
    
    def extract_features(self, tweet: Dict[str, Any]) -> Dict[str, Any]:
        """Extract additional features from tweet."""
        text = tweet.get('text', '')
        
        features = {
            # Text features
            'char_count': len(text),
            'word_count': len(text.split()),
            'hashtag_count': len(re.findall(r'#\w+', text)),
            'mention_count': len(re.findall(r'@\w+', text)),
            'url_count': len(re.findall(r'https?://\S+', text)),
            'emoji_count': len(re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', text)),
            
            # Engagement rate (likes per follower)
            'engagement_rate': (
                tweet.get('like_count', 0) / max(tweet.get('user_followers', 1), 1)
            ),
            
            # Virality score (retweets + likes)
            'virality_score': tweet.get('retweet_count', 0) + tweet.get('like_count', 0),
            
            # Text characteristics
            'has_hashtags': bool(re.search(r'#\w+', text)),
            'has_mentions': bool(re.search(r'@\w+', text)),
            'has_urls': bool(re.search(r'https?://\S+', text)),
            'is_long': len(text) > 280,
            
            # User credibility
            'user_credibility_score': min(
                1.0,
                (tweet.get('user_followers', 0) / 1000000) * 0.5 +
                (1 if tweet.get('user_verified', False) else 0) * 0.5
            ),
        }
        
        return features
    
    def process_tweet(self, tweet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a single tweet."""
        try:
            # Validate
            is_valid, error_msg = self.validate_tweet(tweet)
            if not is_valid:
                self.logger.debug(f"Invalid tweet {tweet.get('tweet_id')}: {error_msg}")
                self.invalid_count += 1
                return None
            
            # Clean text
            tweet['text'] = self.clean_text(tweet['text'])
            
            # Extract features
            features = self.extract_features(tweet)
            
            # Combine tweet data with features
            processed = {
                **tweet,
                **features,
                'processed_at': datetime.now().isoformat(),
                'processing_version': '1.0',
            }
            
            self.processed_count += 1
            
            return processed
            
        except Exception as e:
            self.logger.error(f"Error processing tweet: {e}")
            self.invalid_count += 1
            metrics.record_error('tweet_processing', str(e))
            return None
    
    def store_tweet(self, tweet: Dict[str, Any]) -> bool:
        """Store processed tweet in PostgreSQL."""
        try:
            # Check if already exists
            existing = self.db.fetch_one(
                "SELECT tweet_id FROM tweets WHERE tweet_id = %s",
                (tweet['tweet_id'],)
            )
            
            if existing:
                self.logger.debug(f"Tweet {tweet['tweet_id']} already in database")
                return False
            
            # Build INSERT query manually since we don't have auto-increment ID
            columns = ', '.join(tweet.keys())
            placeholders = ', '.join(['%s'] * len(tweet))
            query = f"INSERT INTO tweets ({columns}) VALUES ({placeholders})"
            
            # Execute insert
            success = self.db.execute(query, tuple(tweet.values()))
            
            if success:
                self.stored_count += 1
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error storing tweet: {e}")
            metrics.record_error('tweet_storage', str(e))
            return False
    
    def process_file(self, filename: str) -> int:
        """Process a single JSONL file from MinIO."""
        try:
            self.logger.info(f"Processing file: {filename}")
            
            # Download file
            data = self.storage.download_data(self.config.bucket_data, filename)
            lines = data.decode('utf-8').strip().split('\n')
            
            stored_count = 0
            
            for line in lines:
                if not line.strip():
                    continue
                
                try:
                    # Parse JSON
                    tweet = json.loads(line)
                    
                    # Process
                    processed = self.process_tweet(tweet)
                    if not processed:
                        continue
                    
                    # Store
                    if self.store_tweet(processed):
                        stored_count += 1
                    
                except json.JSONDecodeError as e:
                    self.logger.error(f"Invalid JSON in {filename}: {e}")
                    continue
            
            self.logger.info(f"Stored {stored_count} tweets from {filename}")
            
            # Mark file as processed in Redis
            self.cache.set_add('processed_files', filename)
            
            # Move file to processed folder
            new_filename = filename.replace('raw/', 'processed/')
            self.storage.upload_data(
                self.config.bucket_data,
                new_filename,
                data,
                content_type='application/x-ndjson'
            )
            
            return stored_count
            
        except Exception as e:
            self.logger.error(f"Error processing file {filename}: {e}")
            metrics.record_error('file_processing', str(e))
            return 0
    
    def get_pending_files(self) -> List[str]:
        """Get list of unprocessed files from MinIO."""
        try:
            # List all raw files
            all_files = self.storage.list_objects(self.config.bucket_data, prefix='raw/tweets_')
            self.logger.info(f"Found {len(all_files)} raw files: {all_files[:3]}")
            
            # Get processed files from Redis
            processed = self.cache.set_members('processed_files')
            self.logger.info(f"Already processed {len(processed)} files: {list(processed)[:3]}")
            
            # Filter to only pending files
            pending = [f for f in all_files if f not in processed]
            self.logger.info(f"Pending files to process: {len(pending)}")
            
            return pending
            
        except Exception as e:
            self.logger.error(f"Error getting pending files: {e}")
            return []
    
    def create_tables(self) -> None:
        """Create database tables if they don't exist."""
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS tweets (
                    tweet_id VARCHAR(50) PRIMARY KEY,
                    content_hash VARCHAR(64) NOT NULL,
                    session_id VARCHAR(50),
                    
                    -- Timestamps
                    created_at TIMESTAMP,
                    collected_at TIMESTAMP,
                    processed_at TIMESTAMP,
                    
                    -- Content
                    text TEXT NOT NULL,
                    text_length INTEGER,
                    lang VARCHAR(10),
                    possibly_sensitive BOOLEAN,
                    
                    -- User
                    user_id VARCHAR(50),
                    username VARCHAR(100),
                    user_name VARCHAR(255),
                    user_description TEXT,
                    user_location VARCHAR(255),
                    user_verified BOOLEAN,
                    user_followers INTEGER,
                    user_following INTEGER,
                    user_created_at TIMESTAMP,
                    
                    -- Engagement
                    retweet_count INTEGER DEFAULT 0,
                    like_count INTEGER DEFAULT 0,
                    reply_count INTEGER DEFAULT 0,
                    quote_count INTEGER DEFAULT 0,
                    view_count INTEGER DEFAULT 0,
                    bookmark_count INTEGER DEFAULT 0,
                    
                    -- Flags
                    is_retweet BOOLEAN DEFAULT FALSE,
                    is_reply BOOLEAN DEFAULT FALSE,
                    is_quote BOOLEAN DEFAULT FALSE,
                    
                    -- Entities
                    hashtags TEXT,
                    hashtags_count INTEGER DEFAULT 0,
                    mentions TEXT,
                    mentions_count INTEGER DEFAULT 0,
                    urls TEXT,
                    urls_count INTEGER DEFAULT 0,
                    media_urls TEXT,
                    media_count INTEGER DEFAULT 0,
                    cashtags TEXT,
                    
                    -- Entity flags
                    has_hashtags BOOLEAN DEFAULT FALSE,
                    has_mentions BOOLEAN DEFAULT FALSE,
                    has_urls BOOLEAN DEFAULT FALSE,
                    has_media BOOLEAN DEFAULT FALSE,
                    
                    -- Features
                    char_count INTEGER,
                    word_count INTEGER,
                    hashtag_count INTEGER,
                    mention_count INTEGER,
                    url_count INTEGER,
                    emoji_count INTEGER,
                    engagement_rate FLOAT,
                    virality_score INTEGER,
                    is_long BOOLEAN,
                    user_credibility_score FLOAT,
                    
                    -- Metadata
                    source VARCHAR(50),
                    search_query VARCHAR(255),
                    processing_version VARCHAR(10),
                    
                    -- Indexes
                    created_at_idx TIMESTAMP,
                    CONSTRAINT unique_content UNIQUE (content_hash)
                );
                
                CREATE INDEX IF NOT EXISTS idx_tweets_created_at ON tweets(created_at);
                CREATE INDEX IF NOT EXISTS idx_tweets_user_id ON tweets(user_id);
                CREATE INDEX IF NOT EXISTS idx_tweets_lang ON tweets(lang);
                CREATE INDEX IF NOT EXISTS idx_tweets_processed_at ON tweets(processed_at);
            """)
            
            self.logger.info("Database tables created/verified")
            
        except Exception as e:
            self.logger.error(f"Error creating tables: {e}")
    
    async def run_continuous(self, interval_seconds: int = 60) -> None:
        """Run ingest processor continuously."""
        self.logger.info(f"Starting continuous processing (interval: {interval_seconds}s)")
        
        # Create tables
        self.create_tables()
        
        while True:
            try:
                # Get pending files
                pending_files = self.get_pending_files()
                
                if not pending_files:
                    self.logger.info("No pending files to process")
                else:
                    self.logger.info(f"Found {len(pending_files)} pending files")
                    
                    # Process each file
                    for filename in pending_files:
                        self.process_file(filename)
                
                # Log statistics
                self.logger.info(
                    f"Session stats - Processed: {self.processed_count}, "
                    f"Invalid: {self.invalid_count}, "
                    f"Stored: {self.stored_count}"
                )
                
                # Wait before next check
                await asyncio.sleep(interval_seconds)
                
            except KeyboardInterrupt:
                self.logger.info("Processor stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Error in processing loop: {e}")
                await asyncio.sleep(60)


async def main():
    """Main entry point."""
    setup_logging()
    logger = get_logger(__name__)
    
    logger.info("Starting Data Ingest Processor Service")
    
    processor = DataIngestProcessor()
    
    # Check for once mode (process pending files then exit)
    ingest_mode = os.getenv('INGEST_MODE', 'continuous')
    
    if ingest_mode == 'once':
        logger.info("🎯 ONCE MODE - Processing pending files then exiting")
        
        try:
            # Create tables
            processor.create_tables()
            
            # Get pending files
            pending_files = processor.get_pending_files()
            
            if not pending_files:
                logger.info("No pending files to process")
            else:
                logger.info(f"Found {len(pending_files)} pending files")
                
                # Process each file
                for filename in pending_files:
                    processor.process_file(filename)
            
            # Log final statistics
            logger.info(
                f"✅ Processing complete - Processed: {processor.processed_count}, "
                f"Invalid: {processor.invalid_count}, "
                f"Stored: {processor.stored_count}"
            )
            
        except Exception as e:
            logger.error(f"Error in once mode: {e}")
        
        logger.info("Ingest shutdown complete (once mode)")
        return
    
    # Continuous mode
    try:
        await processor.run_continuous(interval_seconds=60)
    except KeyboardInterrupt:
        logger.info("Processor stopped")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        logger.info("Processor shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
