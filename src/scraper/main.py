"""
MLOps-enhanced Twitter Scraper Service
Collects tweets and stores them in MinIO with Redis deduplication
Enhanced with anti-bot detection features for 24/7 operation
"""
import asyncio
import json
import hashlib
import random
import re
import html
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
import numpy as np
from twikit import Client, errors

from common import (
    get_config, 
    get_logger, 
    setup_logging,
    metrics,
    MinIOClient,
    RedisCache,
    Database
)


class MLOpsTwitterScraper:
    """Twitter scraper with full MLOps integration and anti-bot detection."""
    
    # User agent pool for rotation
    USER_AGENTS = ['en-US', 'en-GB', 'id-ID', 'ja-JP']
    
    # Anti-bot configuration
    DELAY_MIN = 5.0
    DELAY_MAX = 12.0
    DELAY_JITTER = 0.3
    THINKING_PAUSE_PROBABILITY = 0.15
    THINKING_PAUSE_MIN = 20.0
    THINKING_PAUSE_MAX = 45.0
    
    # Rate limits
    MAX_REQUESTS_PER_HOUR = 30
    MAX_REQUESTS_PER_DAY = 200
    
    def __init__(self):
        """Initialize scraper with MLOps services."""
        self.config = get_config()
        self.logger = get_logger(__name__)
        
        # Initialize services
        self.storage = MinIOClient()
        self.cache = RedisCache()
        self.db = Database()
        
        # Twitter client with rotated user agent
        self.user_agent = random.choice(self.USER_AGENTS)
        self.client = Client(self.user_agent)
        
        # Session tracking
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.collected_count = 0
        self.duplicate_count = 0
        self.error_count = 0
        
        # Rate limiting tracking
        self.request_timestamps: List[datetime] = []
        
        self.logger.info(f"Initialized scraper session: {self.session_id}")
        self.logger.info(f"User agent: {self.user_agent}")
    
    async def human_delay(self, custom_range: Tuple[float, float] = None) -> float:
        """
        Simulate human-like delays with gamma distribution and thinking pauses.
        This is critical for avoiding bot detection in 24/7 operation.
        """
        delay_range = custom_range or (self.DELAY_MIN, self.DELAY_MAX)
        
        # Occasionally add a "thinking pause" to simulate human reading
        if random.random() < self.THINKING_PAUSE_PROBABILITY:
            delay = random.uniform(self.THINKING_PAUSE_MIN, self.THINKING_PAUSE_MAX)
            self.logger.debug(f"💭 Taking thinking pause: {delay:.2f}s")
        else:
            # Gamma distribution (right-skewed, more human-like)
            # Most delays are shorter, some are longer
            shape, scale = 2.0, 2.0
            delay = np.random.gamma(shape, scale)
            
            # Normalize to our range
            delay = delay_range[0] + (delay / 10) * (delay_range[1] - delay_range[0])
            delay = max(delay_range[0], min(delay_range[1], delay))
            
            # Add jitter (random variation)
            jitter = delay * self.DELAY_JITTER * (random.random() - 0.5) * 2
            delay = max(1.0, delay + jitter)
        
        self.logger.debug(f"⏱️  Delay: {delay:.2f}s")
        await asyncio.sleep(delay)
        return delay
    
    def _check_rate_limits(self) -> Tuple[bool, str]:
        """Check if we're within rate limits to avoid detection."""
        now = datetime.now()
        
        # Remove timestamps older than 1 day
        self.request_timestamps = [
            ts for ts in self.request_timestamps 
            if now - ts < timedelta(days=1)
        ]
        
        # Check hourly limit
        hour_ago = now - timedelta(hours=1)
        requests_last_hour = sum(1 for ts in self.request_timestamps if ts > hour_ago)

        if requests_last_hour >= self.MAX_REQUESTS_PER_HOUR:
            return False, f"Hourly limit reached: {requests_last_hour}/{self.MAX_REQUESTS_PER_HOUR}"

        # Check daily limit
        if len(self.request_timestamps) >= self.MAX_REQUESTS_PER_DAY:
            return False, f"Daily limit reached: {len(self.request_timestamps)}/{self.MAX_REQUESTS_PER_DAY}"

        # Best-effort: check Redis flag for adaptive backoff (if Redis wrapper provides get)
        try:
            if hasattr(self, 'cache') and self.cache:
                backoff_flag = self.cache.get('scraper:backoff')
                if backoff_flag:
                    return False, 'backoff'
        except Exception:
            # ignore Redis errors - do not block scraping
            pass

        return True, "OK"
    
    def _record_request(self) -> None:
        """Record a request timestamp for rate limiting."""
        self.request_timestamps.append(datetime.now())
    
    def _rotate_user_agent(self) -> None:
        """Occasionally rotate user agent for better anti-bot evasion."""
        if random.random() < 0.1:  # 10% chance to rotate
            old_agent = self.user_agent
            self.user_agent = random.choice(self.USER_AGENTS)
            if self.user_agent != old_agent:
                self.client = Client(self.user_agent)
                self.logger.info(f"Rotated user agent: {old_agent} -> {self.user_agent}")

    def _build_request_headers(self) -> Dict[str, str]:
        """Build subtle, rotating request headers to reduce fingerprinting."""
        accept_lang = random.choice(['en-US,en;q=0.9', 'id-ID,id;q=0.9', 'en-GB,en;q=0.9', 'ja-JP,ja;q=0.9'])
        headers = {
            'User-Agent': self.user_agent,
            'Accept-Language': accept_lang,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Cache-Control': 'no-cache',
            'Sec-CH-UA': '"Not.A/Brand";v="8", "Chromium";v="120"',
        }
        return headers
    
    async def connect(self) -> bool:
        self.logger.info(f"User agent: {self.user_agent}")
    
    async def connect(self) -> bool:
        """Connect to Twitter with authentication."""
        try:
            # Load cookies from MinIO if exists, otherwise from local file
            try:
                cookies_data = self.storage.download_data('config/cookies.json')
                cookies = json.loads(cookies_data)
                self.client.set_cookies(cookies)
            except Exception as e:
                self.logger.warning(f"Could not load cookies from MinIO: {e}")
                # Fall back to local file
                self.client.load_cookies(self.config.twitter_cookies_file)
            
            # Verify authentication
            me = await self.client.user()
            self.logger.info(f"Authenticated as {me.name} (@{me.screen_name})")
            self.logger.info("Twitter authentication successful")
            return True
            
        except errors.Forbidden:
            self.logger.error("Twitter cookies expired or invalid")
            metrics.record_error('forbidden', 'twitter_auth')
            return False
        except Exception as e:
            self.logger.error(f"Failed to connect to Twitter: {e}")
            metrics.record_error(str(e), 'twitter_auth')
            return False
    
    @staticmethod
    def generate_tweet_hash(text: str) -> str:
        """Generate content hash for deduplication."""
        # Normalize text: remove @mentions, URLs, extra spaces
        normalized = text.lower()
        normalized = re.sub(r'@\w+', '', normalized)
        normalized = re.sub(r'https?://\S+', '', normalized)
        normalized = ' '.join(normalized.split())
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()
    
    @staticmethod
    def clean_text(text: str) -> str:
        """Advanced text cleaning with HTML entity decoding."""
        if not text:
            return ""
        
        # Decode HTML entities
        text = html.unescape(text)
        
        # Remove or replace problematic characters
        replacements = {
            '\u200b': '',  # Zero-width space
            '\u200c': '',  # Zero-width non-joiner
            '\u200d': '',  # Zero-width joiner
            '\ufeff': '',  # Byte order mark
            '\u00a0': ' ', # Non-breaking space
            '\u2026': '...', # Horizontal ellipsis
            '\u2013': '-',   # En dash
            '\u2014': '--',  # Em dash
            '\u2018': "'",   # Left single quotation mark
            '\u2019': "'",   # Right single quotation mark
            '\u201c': '"',   # Left double quotation mark
            '\u201d': '"',   # Right double quotation mark
        }
        
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        return text.strip()
    
    def is_duplicate(self, tweet_id: str, content_hash: str) -> bool:
        """Check if tweet is duplicate using Redis."""
        # Check tweet ID
        if self.cache.set_is_member('processed_tweet_ids', tweet_id):
            return True
        
        # Check content hash
        if self.cache.set_is_member('processed_content_hashes', content_hash):
            return True
        
        return False
    
    def mark_as_processed(self, tweet_id: str, content_hash: str) -> None:
        """Mark tweet as processed in Redis."""
        self.cache.set_add('processed_tweet_ids', tweet_id)
        self.cache.set_add('processed_content_hashes', content_hash)
        # Expire after 90 days
        self.cache.expire('processed_tweet_ids', timedelta(days=90))
        self.cache.expire('processed_content_hashes', timedelta(days=90))
    
    def extract_tweet_data(self, tweet) -> Dict[str, Any]:
        """Extract comprehensive tweet data with entity extraction."""
        tweet_id = str(tweet.id)
        text = tweet.text or ''
        cleaned_text = self.clean_text(text)
        content_hash = self.generate_tweet_hash(cleaned_text)
        
        data = {
            # IDs and hashes
            'tweet_id': tweet_id,
            'content_hash': content_hash,
            'session_id': self.session_id,
            
            # Timestamps
            'created_at': tweet.created_at.isoformat() if hasattr(tweet, 'created_at') and hasattr(tweet.created_at, 'isoformat') else str(tweet.created_at) if hasattr(tweet, 'created_at') else None,
            'collected_at': datetime.now().isoformat(),
            
            # Content
            'text': cleaned_text,
            'text_length': len(cleaned_text),
            'lang': getattr(tweet, 'lang', 'unknown'),
            'possibly_sensitive': getattr(tweet, 'possibly_sensitive', False),
            
            # User
            'user_id': str(tweet.user.id) if hasattr(tweet.user, 'id') else None,
            'username': getattr(tweet.user, 'screen_name', '') or getattr(tweet.user, 'username', ''),
            'user_name': getattr(tweet.user, 'name', ''),
            'user_description': self.clean_text(getattr(tweet.user, 'description', '')),
            'user_location': self.clean_text(getattr(tweet.user, 'location', '')),
            'user_verified': getattr(tweet.user, 'verified', False),
            'user_followers': getattr(tweet.user, 'followers_count', 0),
            'user_following': getattr(tweet.user, 'following_count', 0),
            'user_created_at': str(tweet.user.created_at) if hasattr(tweet.user, 'created_at') else None,
            
            # Engagement
            'retweet_count': getattr(tweet, 'retweet_count', 0),
            'like_count': getattr(tweet, 'favorite_count', 0),
            'reply_count': getattr(tweet, 'reply_count', 0),
            'quote_count': getattr(tweet, 'quote_count', 0),
            'view_count': getattr(tweet, 'view_count', 0),
            'bookmark_count': getattr(tweet, 'bookmark_count', 0),
            
            # Flags
            'is_retweet': bool(getattr(tweet, 'retweeted_tweet', False)),
            'is_reply': bool(getattr(tweet, 'in_reply_to_user_id', False)),
            'is_quote': bool(getattr(tweet, 'quoted_tweet', False)),
            
            # Metadata
            'source': 'twikit',
            'search_query': self.config.twitter_search_query,
            
            # Extracted entities (will be populated below)
            'hashtags': [],
            'hashtags_count': 0,
            'mentions': [],
            'mentions_count': 0,
            'urls': [],
            'urls_count': 0,
            'media_urls': [],
            'media_count': 0,
            'cashtags': [],
            
            # Additional metadata
            'has_media': False,
            'has_urls': False,
            'has_hashtags': False,
            'has_mentions': False,
        }
        
        # Extract entities using regex
        # Hashtags
        hashtag_pattern = r'#[\w\u00c0-\u024f\u1e00-\u1eff]+'
        data['hashtags'] = list(set(re.findall(hashtag_pattern, cleaned_text, re.IGNORECASE)))
        data['hashtags_count'] = len(data['hashtags'])
        data['has_hashtags'] = data['hashtags_count'] > 0
        
        # Mentions
        mention_pattern = r'@[\w\u00c0-\u024f\u1e00-\u1eff]+'
        data['mentions'] = list(set(re.findall(mention_pattern, cleaned_text, re.IGNORECASE)))
        data['mentions_count'] = len(data['mentions'])
        data['has_mentions'] = data['mentions_count'] > 0
        
        # URLs
        url_pattern = r'https?://[^\s]+'
        data['urls'] = list(set(re.findall(url_pattern, cleaned_text)))
        data['urls_count'] = len(data['urls'])
        data['has_urls'] = data['urls_count'] > 0
        
        # Cashtags (stock symbols)
        cashtag_pattern = r'\$[A-Z]{1,6}(?![A-Z])'
        data['cashtags'] = list(set(re.findall(cashtag_pattern, cleaned_text)))
        
        # Try to extract additional data from tweet entities if available
        try:
            if hasattr(tweet, 'entities') and tweet.entities:
                # Enhanced URL extraction
                if hasattr(tweet.entities, 'urls'):
                    expanded_urls = []
                    for url in tweet.entities.urls:
                        if hasattr(url, 'expanded_url'):
                            expanded_urls.append(url.expanded_url)
                    data['urls'].extend(expanded_urls)
                    data['urls'] = list(set(data['urls']))
                    data['urls_count'] = len(data['urls'])
                    data['has_urls'] = data['urls_count'] > 0
                
                # Media extraction
                if hasattr(tweet.entities, 'media'):
                    media_urls = []
                    for media in tweet.entities.media:
                        if hasattr(media, 'media_url'):
                            media_urls.append(media.media_url)
                    data['media_urls'] = media_urls
                    data['media_count'] = len(media_urls)
                    data['has_media'] = data['media_count'] > 0
        except Exception as e:
            self.logger.debug(f"Could not extract entities from tweet {tweet_id}: {e}")
        
        return data
    
    async def collect_batch(self, max_tweets: int = 100) -> List[Dict[str, Any]]:
        """Collect a batch of tweets with anti-bot protection."""
        collected = []
        
        # Check rate limits before starting
        can_proceed, message = self._check_rate_limits()
        if not can_proceed:
            self.logger.warning(f"Rate limit check failed: {message}")
            return collected
        
        try:
            self.logger.info(f"Searching for: {self.config.twitter_search_query}")
            
            # Record request
            self._record_request()
            
            # Build rotating headers and try to use a headers-capable client call if available
            headers = self._build_request_headers()
            try:
                if hasattr(self.client, 'search_tweet_with_headers'):
                    tweets = await self.client.search_tweet_with_headers(
                        self.config.twitter_search_query,
                        'Latest',
                        headers=headers
                    )
                else:
                    # Fallback to standard call
                    tweets = await self.client.search_tweet(
                        self.config.twitter_search_query,
                        'Latest'
                    )
            except Exception as e:
                msg = str(e).lower()
                # Best-effort rate-limit/backoff detection
                if '429' in msg or 'rate' in msg or 'throttl' in msg:
                    self.logger.warning('Rate limit or throttling detected; enabling backoff in Redis')
                    try:
                        if hasattr(self, 'cache') and self.cache:
                            # Store a backoff flag and expiry (best-effort API)
                            try:
                                # prefer set with expiry if available
                                self.cache.set('scraper:backoff', '1')
                                self.cache.expire('scraper:backoff', timedelta(seconds=300))
                                self.cache.set('scraper:backoff_secs', 300)
                                self.cache.expire('scraper:backoff_secs', timedelta(seconds=300))
                            except Exception:
                                # Fallback: try a simple set without expire
                                try:
                                    self.cache.set('scraper:backoff', '1')
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    return collected
                raise
            
            for i, tweet in enumerate(tweets):
                if len(collected) >= max_tweets:
                    break
                
                # Check rate limits periodically
                if i > 0 and i % 5 == 0:
                    can_proceed, message = self._check_rate_limits()
                    if not can_proceed:
                        self.logger.warning(f"Rate limit reached during collection: {message}")
                        break
                
                # Extract data
                tweet_data = self.extract_tweet_data(tweet)
                tweet_id = tweet_data['tweet_id']
                content_hash = tweet_data['content_hash']
                
                # Check for duplicates
                if self.is_duplicate(tweet_id, content_hash):
                    self.duplicate_count += 1
                    self.logger.debug(f"Skipping duplicate: {tweet_id}")
                    continue
                
                # Skip retweets if configured
                if self.config.twitter_exclude_retweets and tweet_data['is_retweet']:
                    continue
                
                # Skip replies if configured
                if self.config.twitter_exclude_replies and tweet_data['is_reply']:
                    continue
                
                # Mark as processed
                self.mark_as_processed(tweet_id, content_hash)
                collected.append(tweet_data)
                self.collected_count += 1
                self._record_request()
                
                # Human-like delay with randomization
                await self.human_delay()
            
            self.logger.info(f"Collected {len(collected)} new tweets")
            for _ in range(len(collected)):
                metrics.record_tweet_collected('twitter')
            
        except Exception as e:
            self.logger.error(f"Error collecting tweets: {e}")
            self.error_count += 1
            metrics.record_error('tweet_collection', str(e))
        
        return collected
    
    def save_to_storage(self, tweets: List[Dict[str, Any]]) -> None:
        """Save tweets to MinIO storage."""
        if not tweets:
            return
        
        try:
            # Save as JSONL (one JSON object per line)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"raw/tweets_{self.session_id}_{timestamp}.jsonl"
            
            # Create JSONL content
            jsonl_content = '\n'.join([json.dumps(tweet, ensure_ascii=False) for tweet in tweets])
            
            # Upload to MinIO
            self.storage.upload_data(
                self.config.bucket_data,
                filename,
                jsonl_content.encode('utf-8'),
                content_type='application/x-ndjson'
            )
            
            self.logger.info(f"Saved {len(tweets)} tweets to MinIO: {filename}")
            metrics.update_storage_size('mlops-data', len(jsonl_content.encode('utf-8')))
            
        except Exception as e:
            self.logger.error(f"Error saving to storage: {e}")
            metrics.record_error('storage_save', str(e))
    
    def save_session_metadata(self) -> None:
        """Save session statistics to MinIO."""
        try:
            metadata = {
                'session_id': self.session_id,
                'started_at': datetime.now().isoformat(),
                'collected_count': self.collected_count,
                'duplicate_count': self.duplicate_count,
                'error_count': self.error_count,
                'search_query': self.config.twitter_search_query,
            }
            
            filename = f"metadata/scraper_{self.session_id}.json"
            self.storage.upload_json(self.config.bucket_data, filename, metadata)
            
            self.logger.info(f"Saved session metadata: {filename}")
            
        except Exception as e:
            self.logger.error(f"Error saving metadata: {e}")
    
    def print_summary(self, tweets: List[Dict[str, Any]] = None) -> None:
        """Print comprehensive collection summary."""
        if not tweets:
            self.logger.info("No tweets to summarize")
            return
        
        try:
            self.logger.info("="*60)
            self.logger.info("📊 COLLECTION SUMMARY")
            self.logger.info("="*60)
            
            # Basic stats
            self.logger.info(f"Total tweets collected: {len(tweets)}")
            unique_users = len(set(t.get('user_id') for t in tweets if t.get('user_id')))
            self.logger.info(f"Unique users: {unique_users}")
            self.logger.info(f"Search query: '{self.config.twitter_search_query}'")
            
            # Engagement statistics
            total_likes = sum(t.get('like_count', 0) for t in tweets)
            total_retweets = sum(t.get('retweet_count', 0) for t in tweets)
            total_replies = sum(t.get('reply_count', 0) for t in tweets)
            total_views = sum(t.get('view_count', 0) for t in tweets)
            avg_likes = total_likes / len(tweets) if tweets else 0
            
            self.logger.info("")
            self.logger.info("📈 ENGAGEMENT STATISTICS")
            self.logger.info(f"Total likes: {total_likes:,}")
            self.logger.info(f"Total retweets: {total_retweets:,}")
            self.logger.info(f"Total replies: {total_replies:,}")
            self.logger.info(f"Total views: {total_views:,}")
            self.logger.info(f"Average likes per tweet: {avg_likes:.1f}")
            
            # Content analysis
            avg_length = sum(t.get('text_length', 0) for t in tweets) / len(tweets) if tweets else 0
            has_hashtags = sum(1 for t in tweets if t.get('has_hashtags'))
            has_mentions = sum(1 for t in tweets if t.get('has_mentions'))
            has_urls = sum(1 for t in tweets if t.get('has_urls'))
            has_media = sum(1 for t in tweets if t.get('has_media'))
            
            self.logger.info("")
            self.logger.info("📝 CONTENT ANALYSIS")
            self.logger.info(f"Average text length: {avg_length:.0f} characters")
            self.logger.info(f"Tweets with hashtags: {has_hashtags} ({has_hashtags/len(tweets)*100:.1f}%)")
            self.logger.info(f"Tweets with mentions: {has_mentions} ({has_mentions/len(tweets)*100:.1f}%)")
            self.logger.info(f"Tweets with URLs: {has_urls} ({has_urls/len(tweets)*100:.1f}%)")
            self.logger.info(f"Tweets with media: {has_media} ({has_media/len(tweets)*100:.1f}%)")
            
            # Language distribution
            langs = {}
            for t in tweets:
                lang = t.get('lang', 'unknown')
                langs[lang] = langs.get(lang, 0) + 1
            
            if langs:
                self.logger.info("")
                self.logger.info("🌍 LANGUAGE DISTRIBUTION")
                sorted_langs = sorted(langs.items(), key=lambda x: x[1], reverse=True)[:5]
                for lang, count in sorted_langs:
                    self.logger.info(f"{lang}: {count} ({count/len(tweets)*100:.1f}%)")
            
            # Top hashtags
            all_hashtags = []
            for t in tweets:
                if t.get('hashtags'):
                    all_hashtags.extend(t['hashtags'])
            
            if all_hashtags:
                from collections import Counter
                top_hashtags = Counter(all_hashtags).most_common(10)
                self.logger.info("")
                self.logger.info("🏷️  TOP HASHTAGS")
                for hashtag, count in top_hashtags:
                    self.logger.info(f"{hashtag}: {count}")
            
            # Top mentions
            all_mentions = []
            for t in tweets:
                if t.get('mentions'):
                    all_mentions.extend(t['mentions'])
            
            if all_mentions:
                from collections import Counter
                top_mentions = Counter(all_mentions).most_common(5)
                self.logger.info("")
                self.logger.info("👥 TOP MENTIONS")
                for mention, count in top_mentions:
                    self.logger.info(f"{mention}: {count}")
            
            # Sample tweet
            if tweets:
                self.logger.info("")
                self.logger.info("📄 SAMPLE TWEET")
                sample = tweets[0]
                text = sample.get('text', 'N/A')
                if len(text) > 100:
                    text = text[:100] + "..."
                self.logger.info(f"ID: {sample.get('tweet_id', 'N/A')}")
                self.logger.info(f"Text: {text}")
                self.logger.info(f"User: {sample.get('user_name', 'N/A')} (@{sample.get('username', 'N/A')})")
                self.logger.info(f"Likes: {sample.get('like_count', 0)}")
            
            self.logger.info("="*60)
            
        except Exception as e:
            self.logger.error(f"Error generating summary: {e}")
            self.logger.info(f"Collected {len(tweets)} tweets total")
    
    async def run_continuous(self, interval_seconds: int = 300) -> None:
        """Run scraper continuously with randomized intervals for anti-bot protection."""
        self.logger.info(f"Starting continuous scraping (base interval: {interval_seconds}s)")
        self.logger.info(f"Anti-bot features: ✅ Human delays, ✅ Rate limiting, ✅ User agent rotation")
        # Use a Poisson process (exponential inter-arrival) to randomize exact start times
        mean_interval = float(interval_seconds)
        while True:
            try:
                # Occasionally rotate user agent
                self._rotate_user_agent()

                # Determine inter-run interval from exponential distribution
                wait = random.expovariate(1.0 / mean_interval)
                wait = max(5.0, min(wait, mean_interval * 3))
                self.logger.debug(f"Sleeping {wait:.1f}s before next collection (poisson)")
                await asyncio.sleep(wait)

                # Collect batch
                tweets = await self.collect_batch(max_tweets=100)

                # Save to storage and small micro-pauses to avoid bursty uploads
                if tweets:
                    self.save_to_storage(tweets)
                    # micro-pause to reduce storage burstiness
                    await asyncio.sleep(random.uniform(0.2, 0.8))
                    self.save_session_metadata()
                    # Print summary statistics
                    self.print_summary(tweets)

                # Log stats
                self.logger.info(
                    f"Session stats - Collected: {self.collected_count}, "
                    f"Duplicates: {self.duplicate_count}, "
                    f"Errors: {self.error_count}"
                )

            except KeyboardInterrupt:
                self.logger.info("Scraper stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Error in scraping loop: {e}")
                self.error_count += 1
                # Exponential backoff on error: 1-3 minutes
                error_delay = random.uniform(60, 180)
                self.logger.info(f"Waiting {error_delay:.0f}s before retry...")
                await asyncio.sleep(error_delay)


async def main():
    """Main entry point."""
    # Setup logging
    setup_logging()
    logger = get_logger(__name__)
    
    logger.info("Starting MLOps Twitter Scraper Service")
    
    # Initialize scraper
    scraper = MLOpsTwitterScraper()
    
    # Connect to Twitter
    if not await scraper.connect():
        logger.error("Failed to connect to Twitter. Exiting.")
        sys.exit(1)  # Exit dengan error code 1 agar Airflow detect sebagai failure
    
    # Check for burst mode (run once then exit)
    scraper_mode = os.getenv('SCRAPER_MODE', 'continuous')
    
    if scraper_mode == 'burst':
        logger.info("🎯 BURST MODE - Running single collection session")
        max_tweets = int(os.getenv('TWITTER_MAX_TWEETS', '50'))
        
        try:
            # Collect batch
            tweets = await scraper.collect_batch(max_tweets=max_tweets)
            
            # Save to storage
            if tweets:
                scraper.save_to_storage(tweets)
                scraper.save_session_metadata()
                scraper.print_summary(tweets)
                logger.info(f"✅ Burst mode complete: {len(tweets)} tweets collected")
            else:
                logger.warning("⚠️  No tweets collected in burst mode")
                
        except Exception as e:
            logger.error(f"Error in burst mode: {e}")
            scraper.save_session_metadata()
        
        logger.info("Scraper shutdown complete (burst mode)")
        return
    
    # Continuous mode
    try:
        await scraper.run_continuous(interval_seconds=300)  # Every 5 minutes
    except KeyboardInterrupt:
        logger.info("Scraper stopped")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        scraper.save_session_metadata()
        logger.info("Scraper shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
