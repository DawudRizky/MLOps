"""
Intelligent Scheduler Service for Twitter Scraper
Simulates human-like activity patterns with scheduled bursts
Orchestrates ephemeral Docker containers in a cascade pipeline
"""
import asyncio
import random
import os
import subprocess
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum

from common import (
    get_config,
    get_logger,
    setup_logging,
    metrics,
    RedisCache
)


class DayType(Enum):
    """Day type classification for different activity patterns."""
    WEEKDAY = "weekday"
    WEEKEND = "weekend"
    HOLIDAY = "holiday"  # Future: can add Indonesian holidays


class ActivityWindow:
    """Represents a time window for scraping activity."""
    
    def __init__(
        self,
        name: str,
        start_hour: int,
        start_minute: int,
        duration_min: int,
        duration_max: int,
        tweets_min: int,
        tweets_max: int,
        variance_minutes: int = 15,
        skip_probability: float = 0.05
    ):
        """
        Initialize activity window.
        
        Args:
            name: Window name (e.g., "morning", "lunch")
            start_hour: Base start hour (24-hour format)
            start_minute: Base start minute
            duration_min: Minimum session duration (seconds)
            duration_max: Maximum session duration (seconds)
            tweets_min: Minimum tweets to collect
            tweets_max: Maximum tweets to collect
            variance_minutes: Time variance ±minutes for randomization
            skip_probability: Probability of skipping this window (0.0-1.0)
        """
        self.name = name
        self.base_start = time(start_hour, start_minute)
        self.duration_min = duration_min
        self.duration_max = duration_max
        self.tweets_min = tweets_min
        self.tweets_max = tweets_max
        self.variance_minutes = variance_minutes
        self.skip_probability = skip_probability
    
    def get_randomized_start(self) -> time:
        """Get randomized start time with variance."""
        # Add random variance
        variance_seconds = random.randint(
            -self.variance_minutes * 60,
            self.variance_minutes * 60
        )
        
        # Calculate new time
        base_datetime = datetime.combine(datetime.today(), self.base_start)
        randomized = base_datetime + timedelta(seconds=variance_seconds)
        
        return randomized.time()
    
    def get_randomized_duration(self) -> int:
        """Get randomized session duration in seconds."""
        return random.randint(self.duration_min, self.duration_max)
    
    def get_randomized_tweets(self) -> int:
        """Get randomized tweet target."""
        return random.randint(self.tweets_min, self.tweets_max)
    
    def should_skip(self) -> bool:
        """Decide if this window should be skipped (simulates human unpredictability)."""
        return random.random() < self.skip_probability
    
    def is_active(self, current_time: time) -> bool:
        """Check if current time is within this window's possible range."""
        # Calculate earliest and latest possible start times
        base_datetime = datetime.combine(datetime.today(), self.base_start)
        earliest = (base_datetime - timedelta(minutes=self.variance_minutes)).time()
        latest = (base_datetime + timedelta(minutes=self.variance_minutes + self.duration_max // 60)).time()
        
        # Handle midnight wraparound
        if earliest > latest:
            return current_time >= earliest or current_time <= latest
        else:
            return earliest <= current_time <= latest


class HumanBehaviorSimulator:
    """Simulates realistic human browsing patterns."""
    
    @staticmethod
    def is_sleeping_hours(hour: int) -> bool:
        """Check if it's typical sleeping hours (midnight-6am)."""
        return 0 <= hour < 6
    
    @staticmethod
    def is_work_hours(hour: int, weekday: int) -> bool:
        """Check if it's work hours (9am-5pm on weekdays)."""
        return weekday < 5 and 9 <= hour < 17
    
    @staticmethod
    def get_activity_probability(current_time: datetime) -> float:
        """
        Calculate probability of activity based on time and day.
        Returns 0.0-1.0 probability.
        """
        hour = current_time.hour
        weekday = current_time.weekday()  # 0=Monday, 6=Sunday
        
        # Sleep hours - very low activity
        if HumanBehaviorSimulator.is_sleeping_hours(hour):
            return 0.02  # 2% - occasional insomnia/night owl
        
        # Work hours (weekdays) - low activity
        if HumanBehaviorSimulator.is_work_hours(hour, weekday):
            return 0.15  # 15% - quick breaks
        
        # Peak hours (morning, lunch, evening)
        if hour in [7, 8, 12, 13, 18, 19, 21, 22]:
            # Higher on weekends
            return 0.85 if weekday >= 5 else 0.75
        
        # Weekend - generally more active
        if weekday >= 5:
            return 0.50
        
        # Default - moderate activity
        return 0.30
    
    @staticmethod
    def should_take_break(session_duration: int) -> bool:
        """
        Decide if user should take a break during session.
        Longer sessions = higher break probability.
        """
        # 10% base probability, +1% per minute
        probability = 0.10 + (session_duration / 60) * 0.01
        return random.random() < probability
    
    @staticmethod
    def get_break_duration() -> int:
        """Get random break duration (30s-3min)."""
        return random.randint(30, 180)


class DockerOrchestrator:
    """Orchestrates ephemeral Docker containers for the ML pipeline."""
    
    def __init__(self, logger):
        """Initialize orchestrator."""
        self.logger = logger
        # Network name includes project prefix (twt_)
        self.docker_network = "twt_mlops-network"
    
    async def run_container(
        self,
        service_name: str,
        image_name: str,
        command: Optional[List[str]] = None,
        environment: Optional[Dict[str, str]] = None,
        timeout: int = 3600
    ) -> Dict[str, any]:
        """
        Run an ephemeral Docker container and wait for completion.
        
        Args:
            service_name: Name of the service (for logging)
            image_name: Docker image name
            command: Optional command to run
            environment: Optional environment variables
            timeout: Maximum runtime in seconds
            
        Returns:
            Dict with status, exit_code, stdout, stderr
        """
        self.logger.info(f"🚀 Spawning ephemeral {service_name} container")
        
        # Build docker run command
        docker_cmd = [
            "docker", "run",
            "--rm",  # Remove after completion
            "--network", self.docker_network,
            "--name", f"twt-{service_name}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        ]
        
        # Add environment variables
        if environment:
            for key, value in environment.items():
                docker_cmd.extend(["-e", f"{key}={value}"])
        
        # Add volume mounts (use absolute host paths)
        # The scheduler runs in a container, but spawns sibling containers on the host
        # So we need to use host paths, not container paths
        host_project_root = "/root/twt"  # Host path where project is mounted
        docker_cmd.extend([
            "-v", f"{host_project_root}/cookies.json:/app/cookies.json:ro",
            "-v", f"{host_project_root}/data/raw:/app/data/raw",
        ])
        
        # Add image
        docker_cmd.append(image_name)
        
        # Add command if provided
        if command:
            docker_cmd.extend(command)
        
        # Log command
        self.logger.debug(f"Command: {' '.join(docker_cmd)}")
        
        try:
            # Run container
            start_time = datetime.now()
            
            process = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Wait with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                
                duration = (datetime.now() - start_time).total_seconds()
                exit_code = process.returncode
                
                if exit_code == 0:
                    self.logger.info(f"✅ {service_name} completed successfully ({duration:.1f}s)")
                    return {
                        'success': True,
                        'exit_code': exit_code,
                        'duration': duration,
                        'stdout': stdout.decode('utf-8', errors='ignore'),
                        'stderr': stderr.decode('utf-8', errors='ignore')
                    }
                else:
                    self.logger.error(f"❌ {service_name} failed with exit code {exit_code}")
                    self.logger.error(f"Stderr: {stderr.decode('utf-8', errors='ignore')[:500]}")
                    return {
                        'success': False,
                        'exit_code': exit_code,
                        'duration': duration,
                        'stdout': stdout.decode('utf-8', errors='ignore'),
                        'stderr': stderr.decode('utf-8', errors='ignore')
                    }
                    
            except asyncio.TimeoutError:
                self.logger.error(f"⏱️  {service_name} timed out after {timeout}s")
                process.kill()
                await process.wait()
                
                return {
                    'success': False,
                    'exit_code': -1,
                    'duration': timeout,
                    'error': 'Timeout'
                }
                
        except Exception as e:
            self.logger.error(f"❌ Error running {service_name} container: {e}")
            return {
                'success': False,
                'exit_code': -1,
                'duration': 0,
                'error': str(e)
            }


class ScraperScheduler:
    """Intelligent scheduler for Twitter scraper with human-like patterns."""
    
    # Weekday activity windows (Jakarta timezone)
    WEEKDAY_WINDOWS = [
        ActivityWindow(
            name="morning",
            start_hour=7, start_minute=15,
            duration_min=600, duration_max=900,  # 10-15 minutes
            tweets_min=35, tweets_max=50,
            variance_minutes=15,
            skip_probability=0.05  # 5% chance to skip
        ),
        ActivityWindow(
            name="lunch",
            start_hour=12, start_minute=45,
            duration_min=540, duration_max=840,  # 9-14 minutes
            tweets_min=25, tweets_max=40,
            variance_minutes=20,
            skip_probability=0.08  # 8% chance to skip
        ),
        ActivityWindow(
            name="evening",
            start_hour=18, start_minute=20,
            duration_min=660, duration_max=960,  # 11-16 minutes
            tweets_min=30, tweets_max=45,
            variance_minutes=15,
            skip_probability=0.06  # 6% chance to skip
        ),
        ActivityWindow(
            name="night",
            start_hour=21, start_minute=30,
            duration_min=600, duration_max=840,  # 10-14 minutes
            tweets_min=25, tweets_max=40,
            variance_minutes=18,
            skip_probability=0.10  # 10% chance to skip (tired)
        ),
    ]
    
    # Weekend activity windows (slightly different pattern)
    WEEKEND_WINDOWS = [
        ActivityWindow(
            name="late_morning",
            start_hour=9, start_minute=30,  # Sleep in!
            duration_min=600, duration_max=1020,  # 10-17 minutes
            tweets_min=35, tweets_max=50,
            variance_minutes=25,
            skip_probability=0.12  # Higher skip - weekends are unpredictable
        ),
        ActivityWindow(
            name="afternoon",
            start_hour=14, start_minute=15,
            duration_min=540, duration_max=900,  # 9-15 minutes
            tweets_min=25, tweets_max=40,
            variance_minutes=30,
            skip_probability=0.15  # Might be out doing activities
        ),
        ActivityWindow(
            name="evening",
            start_hour=19, start_minute=0,
            duration_min=660, duration_max=1020,  # 11-17 minutes
            tweets_min=30, tweets_max=45,
            variance_minutes=20,
            skip_probability=0.08
        ),
        ActivityWindow(
            name="late_night",
            start_hour=22, start_minute=45,  # Weekend night owl
            duration_min=600, duration_max=900,  # 10-15 minutes
            tweets_min=25, tweets_max=40,
            variance_minutes=25,
            skip_probability=0.20  # Often might skip if out
        ),
    ]
    
    def __init__(self):
        """Initialize scheduler."""
        self.config = get_config()
        self.logger = get_logger(__name__)
        self.cache = RedisCache()
        self.behavior = HumanBehaviorSimulator()
        self.orchestrator = DockerOrchestrator(self.logger)
        
        # State tracking
        self.current_window: Optional[ActivityWindow] = None
        self.next_scheduled_time: Optional[datetime] = None
        self.sessions_today = 0
        self.tweets_today = 0
        self.last_session_date: Optional[datetime] = None
        
        # Load state from Redis if exists
        self._load_state()
        
        self.logger.info("Scheduler initialized with Docker orchestration")
        self.logger.info("Pipeline: Scraper → Ingest → Quality Gate → Trainer")
    
    def _load_state(self) -> None:
        """Load scheduler state from Redis."""
        try:
            state = self.cache.get_json('scheduler:state')
            if state:
                self.sessions_today = state.get('sessions_today', 0)
                self.tweets_today = state.get('tweets_today', 0)
                last_date = state.get('last_session_date')
                if last_date:
                    self.last_session_date = datetime.fromisoformat(last_date)
                
                # Reset if it's a new day
                if self.last_session_date and self.last_session_date.date() != datetime.now().date():
                    self.sessions_today = 0
                    self.tweets_today = 0
                    self.logger.info("New day - reset session counters")
        except Exception as e:
            self.logger.warning(f"Could not load scheduler state: {e}")
    
    def _save_state(self) -> None:
        """Save scheduler state to Redis."""
        try:
            state = {
                'sessions_today': self.sessions_today,
                'tweets_today': self.tweets_today,
                'last_session_date': datetime.now().isoformat(),
            }
            self.cache.set_json('scheduler:state', state, expire=timedelta(days=2))
        except Exception as e:
            self.logger.warning(f"Could not save scheduler state: {e}")
    
    def get_day_type(self, date: datetime) -> DayType:
        """Determine day type (weekday/weekend/holiday)."""
        weekday = date.weekday()
        
        # TODO: Add Indonesian holiday detection
        # For now, just weekday/weekend
        if weekday >= 5:
            return DayType.WEEKEND
        return DayType.WEEKDAY
    
    def get_windows_for_day(self, day_type: DayType) -> List[ActivityWindow]:
        """Get activity windows for given day type."""
        if day_type == DayType.WEEKEND:
            return self.WEEKEND_WINDOWS
        return self.WEEKDAY_WINDOWS
    
    def get_next_window(self) -> Optional[Tuple[ActivityWindow, datetime]]:
        """
        Get next scheduled activity window.
        Returns (window, scheduled_datetime) or None.
        """
        now = datetime.now()
        current_time = now.time()
        day_type = self.get_day_type(now)
        windows = self.get_windows_for_day(day_type)
        
        # Find next window
        for window in windows:
            # Check if window should be skipped
            if window.should_skip():
                self.logger.info(f"Skipping {window.name} window (random skip)")
                continue
            
            # Get randomized start time for this window
            start_time = window.get_randomized_start()
            
            # If start time is in the future today
            if start_time > current_time:
                scheduled = datetime.combine(now.date(), start_time)
                return window, scheduled
        
        # No more windows today, get first window of tomorrow
        tomorrow = now + timedelta(days=1)
        tomorrow_type = self.get_day_type(tomorrow)
        tomorrow_windows = self.get_windows_for_day(tomorrow_type)
        
        if tomorrow_windows:
            first_window = tomorrow_windows[0]
            if not first_window.should_skip():
                start_time = first_window.get_randomized_start()
                scheduled = datetime.combine(tomorrow.date(), start_time)
                return first_window, scheduled
        
        return None
    
    async def wait_until(self, target_time: datetime) -> None:
        """Wait until target time with periodic logging."""
        while datetime.now() < target_time:
            remaining = (target_time - datetime.now()).total_seconds()
            
            if remaining > 3600:  # More than 1 hour
                self.logger.info(f"💤 Sleeping until {target_time.strftime('%H:%M')} ({remaining/3600:.1f}h)")
                await asyncio.sleep(1800)  # Check every 30 minutes
            elif remaining > 60:  # More than 1 minute
                self.logger.info(f"💤 Sleeping until {target_time.strftime('%H:%M')} ({remaining/60:.1f}m)")
                await asyncio.sleep(60)  # Check every minute
            else:
                await asyncio.sleep(remaining)
                break
    
    async def run_scraping_session(
        self,
        window: ActivityWindow,
        max_duration: int,
        max_tweets: int
    ) -> Dict[str, any]:
        """
        Run a scraping session using ephemeral Docker containers in cascade.
        
        Pipeline:
        1. Scraper container (ephemeral) - Collects tweets to MinIO
        2. Ingest container (ephemeral) - Processes JSONL to PostgreSQL
        3. Quality Gate container (ephemeral) - Validates data quality
        4. Trainer container (ephemeral) - Trains model if quality passes
        
        Args:
            window: Activity window configuration
            max_duration: Maximum session duration (seconds)
            max_tweets: Maximum tweets to collect
            
        Returns:
            Session statistics dict
        """
        self.logger.info(f"🟢 Starting {window.name} session (CASCADE PIPELINE)")
        self.logger.info(f"   Target: {max_tweets} tweets in ~{max_duration/60:.0f} minutes")
        
        session_start = datetime.now()
        pipeline_results = {
            'window': window.name,
            'session_start': session_start.isoformat(),
            'scraper': None,
            'ingest': None,
            'quality_gate': None,
            'trainer': None
        }
        
        try:
            # Common environment variables
            base_env = {
                'SERVICE_NAME': 'ephemeral',
                'ENVIRONMENT': self.config.environment,
                'MINIO_ENDPOINT': 'minio:9000',
                'MINIO_ACCESS_KEY': self.config.minio_access_key,
                'MINIO_SECRET_KEY': self.config.minio_secret_key,
                'REDIS_HOST': 'redis',
                'REDIS_PORT': '6379',
                'POSTGRES_HOST': 'postgres',
                'POSTGRES_PORT': '5432',
                'POSTGRES_DB': 'mlflow',
                'POSTGRES_USER': 'mlflow',
                'POSTGRES_PASSWORD': 'mlflow123',
                'LOG_LEVEL': 'INFO',
            }
            
            # ===================================================================
            # STEP 1: SCRAPER - Collect tweets
            # ===================================================================
            self.logger.info("📡 Step 1/4: Running SCRAPER")
            
            scraper_env = {
                **base_env,
                'SERVICE_NAME': 'scraper',
                'TWITTER_COOKIES_FILE': '/app/cookies.json',
                'TWITTER_SEARCH_QUERY': self.config.twitter_search_query,
                'TWITTER_MAX_TWEETS': str(max_tweets),
                'TWITTER_EXCLUDE_RETWEETS': 'true',
                'TWITTER_EXCLUDE_REPLIES': 'true',
                'SCRAPER_MODE': 'burst',  # Run once then exit
                'SCRAPER_DURATION': str(max_duration),
            }
            
            scraper_result = await self.orchestrator.run_container(
                service_name='scraper',
                image_name='twt-scraper:latest',
                environment=scraper_env,
                timeout=max_duration + 300  # Add 5 min buffer
            )
            
            pipeline_results['scraper'] = scraper_result
            
            if not scraper_result['success']:
                self.logger.error("❌ Scraper failed, aborting pipeline")
                return {
                    **pipeline_results,
                    'success': False,
                    'stage_failed': 'scraper',
                    'error': scraper_result.get('error', 'Scraper failed')
                }
            
            self.logger.info(f"✅ Scraper completed ({scraper_result['duration']:.1f}s)")
            
            # Small delay before next step
            await asyncio.sleep(random.uniform(2, 5))
            
            # ===================================================================
            # STEP 2: INGEST - Process collected files
            # ===================================================================
            self.logger.info("📥 Step 2/4: Running INGEST")
            
            ingest_env = {
                **base_env,
                'SERVICE_NAME': 'ingest',
                'INGEST_MODE': 'once',  # Process pending files then exit
            }
            
            ingest_result = await self.orchestrator.run_container(
                service_name='ingest',
                image_name='twt-ingest:latest',
                environment=ingest_env,
                timeout=600  # 10 minutes max
            )
            
            pipeline_results['ingest'] = ingest_result
            
            if not ingest_result['success']:
                self.logger.warning("⚠️  Ingest failed, but continuing pipeline")
            else:
                self.logger.info(f"✅ Ingest completed ({ingest_result['duration']:.1f}s)")
            
            await asyncio.sleep(random.uniform(2, 5))
            
            # ===================================================================
            # STEP 3: QUALITY GATE - Validate data quality
            # ===================================================================
            self.logger.info("🔍 Step 3/4: Running QUALITY GATE")
            
            quality_env = {
                **base_env,
                'SERVICE_NAME': 'quality-gate',
                'QUALITY_MODE': 'once',  # Validate then exit
            }
            
            quality_result = await self.orchestrator.run_container(
                service_name='quality-gate',
                image_name='twt-quality-gate:latest',
                environment=quality_env,
                timeout=300  # 5 minutes max
            )
            
            pipeline_results['quality_gate'] = quality_result
            
            if not quality_result['success']:
                self.logger.warning("⚠️  Quality gate failed")
            else:
                self.logger.info(f"✅ Quality gate completed ({quality_result['duration']:.1f}s)")
            
            await asyncio.sleep(random.uniform(2, 5))
            
            # ===================================================================
            # STEP 4: TRAINER - Train model (if quality passed)
            # ===================================================================
            self.logger.info("🎓 Step 4/4: Running TRAINER")
            
            trainer_env = {
                **base_env,
                'SERVICE_NAME': 'trainer',
                'TRAINER_MODE': 'once',  # Train once then exit
                'MLFLOW_TRACKING_URI': 'http://mlflow:5000',
                # MLflow S3/MinIO artifact storage credentials
                'AWS_ACCESS_KEY_ID': self.config.minio_access_key,
                'AWS_SECRET_ACCESS_KEY': self.config.minio_secret_key,
                'MLFLOW_S3_ENDPOINT_URL': 'http://minio:9000',
            }
            
            trainer_result = await self.orchestrator.run_container(
                service_name='trainer',
                image_name='twt-trainer:latest',
                environment=trainer_env,
                timeout=3600  # 1 hour max for training
            )
            
            pipeline_results['trainer'] = trainer_result
            
            if not trainer_result['success']:
                self.logger.warning("⚠️  Trainer did not complete (might be skipped by quality gate)")
            else:
                self.logger.info(f"✅ Trainer completed ({trainer_result['duration']:.1f}s)")
            
            # ===================================================================
            # SESSION COMPLETE
            # ===================================================================
            total_duration = (datetime.now() - session_start).total_seconds()
            
            self.logger.info(f"🎉 {window.name} CASCADE PIPELINE COMPLETE")
            self.logger.info(f"   Total duration: {total_duration/60:.1f} minutes")
            self.logger.info(f"   Scraper: {'✅' if scraper_result['success'] else '❌'}")
            self.logger.info(f"   Ingest: {'✅' if ingest_result['success'] else '❌'}")
            self.logger.info(f"   Quality: {'✅' if quality_result['success'] else '❌'}")
            self.logger.info(f"   Trainer: {'✅' if trainer_result['success'] else '⏭️ '}")
            
            # Update statistics
            self.sessions_today += 1
            # Note: Can't easily count tweets from container, estimate based on target
            self.tweets_today += max_tweets  # Approximation
            self._save_state()
            
            # Record metrics
            metrics.record_metric('scheduler_session_complete', 1, {'window': window.name})
            metrics.record_metric('scheduler_pipeline_duration', total_duration, {'window': window.name})
            
            return {
                **pipeline_results,
                'success': True,
                'total_duration': total_duration,
                'tweets_estimated': max_tweets,
                'timestamp': session_start.isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"❌ Error in pipeline: {e}", exc_info=True)
            metrics.record_error('scheduler_pipeline', str(e))
            
            return {
                **pipeline_results,
                'success': False,
                'stage_failed': 'scheduler',
                'duration': (datetime.now() - session_start).total_seconds(),
                'error': str(e)
            }
    
    async def run(self) -> None:
        """Main scheduler loop."""
        self.logger.info("=" * 60)
        self.logger.info("🚀 Starting Intelligent Scraper Scheduler")
        self.logger.info("=" * 60)
        self.logger.info("Strategy: Human-like scheduled bursts")
        self.logger.info(f"Weekday windows: {len(self.WEEKDAY_WINDOWS)}")
        self.logger.info(f"Weekend windows: {len(self.WEEKEND_WINDOWS)}")
        self.logger.info("=" * 60)
        
        # Check for test/immediate mode
        test_mode = os.getenv('SCHEDULER_TEST_MODE', 'false').lower() == 'true'
        
        if test_mode:
            self.logger.info("🧪 TEST MODE ENABLED - Running immediately!")
            # Use first weekday window but trigger NOW
            window = self.WEEKDAY_WINDOWS[0]
            duration = window.get_randomized_duration()
            tweets = window.get_randomized_tweets()
            
            self.logger.info(f"📡 Test session: {window.name}")
            self.logger.info(f"   Duration: {duration/60:.1f} minutes")
            self.logger.info(f"   Target tweets: {tweets}")
            
            result = await self.run_scraping_session(window, duration, tweets)
            
            if result['success']:
                self.logger.info(f"✅ Test session successful!")
                self.logger.info(f"   Scraper: {'✅' if result['scraper']['success'] else '❌'}")
                self.logger.info(f"   Ingest: {'✅' if result['ingest']['success'] else '❌'}")
                self.logger.info(f"   Quality: {'✅' if result['quality_gate']['success'] else '❌'}")
            else:
                self.logger.error(f"❌ Test session failed: {result.get('error', 'Unknown')}")
            
            self.logger.info("🧪 Test mode complete. Exiting.")
            return
        
        # Normal scheduled mode
        while True:
            try:
                # Get next scheduled window
                next_window_info = self.get_next_window()
                
                if not next_window_info:
                    self.logger.warning("No upcoming windows scheduled. Waiting 1 hour...")
                    await asyncio.sleep(3600)
                    continue
                
                window, scheduled_time = next_window_info
                
                # Log schedule
                now = datetime.now()
                wait_seconds = (scheduled_time - now).total_seconds()
                
                self.logger.info("")
                self.logger.info(f"📅 Next session: {window.name}")
                self.logger.info(f"   Scheduled: {scheduled_time.strftime('%Y-%m-%d %H:%M:%S')}")
                self.logger.info(f"   Waiting: {wait_seconds/3600:.1f} hours")
                self.logger.info(f"   Today's stats: {self.sessions_today} sessions, {self.tweets_today} tweets")
                
                # Wait until scheduled time
                await self.wait_until(scheduled_time)
                
                # Get session parameters
                duration = window.get_randomized_duration()
                tweets = window.get_randomized_tweets()
                
                # Run session
                result = await self.run_scraping_session(window, duration, tweets)
                
                # Log result
                if result['success']:
                    self.logger.info(f"✅ Session successful")
                else:
                    self.logger.error(f"❌ Session failed: {result.get('error', 'Unknown')}")
                
                # Small delay before scheduling next
                await asyncio.sleep(60)
                
            except KeyboardInterrupt:
                self.logger.info("Scheduler stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                # Wait before retrying
                await asyncio.sleep(300)  # 5 minutes


async def main():
    """Main entry point."""
    setup_logging()
    logger = get_logger(__name__)
    
    logger.info("Starting Scheduler Service")
    
    scheduler = ScraperScheduler()
    
    try:
        await scheduler.run()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        logger.info("Scheduler shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
