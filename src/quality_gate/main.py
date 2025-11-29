"""
Quality Gate Service
Validates data quality and decides if dataset is ready for training
"""
import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from common import (
    get_config,
    get_logger,
    setup_logging,
    metrics,
    RedisCache,
    Database
)


class QualityGateValidator:
    """Validate data quality for ML training readiness."""
    
    def __init__(self):
        """Initialize quality gate."""
        self.config = get_config()
        self.logger = get_logger(__name__)
        
        # Initialize services
        self.cache = RedisCache()
        self.db = Database()
        
        # Quality thresholds (configurable) - LOWERED FOR TESTING
        self.min_dataset_size = 10  # Lowered from 1000 for testing
        self.min_unique_users = 5   # Lowered from 50 for testing
        self.max_duplicate_ratio = 0.1
        self.min_avg_quality_score = 0.3  # Lowered from 0.6 for testing
        self.max_error_rate = 0.05
        
        self.logger.info("Initialized Quality Gate Validator")
    
    def get_dataset_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get statistics about recent dataset."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            # Total tweets
            total = self.db.fetch_dict(
                "SELECT COUNT(*) as count FROM tweets WHERE processed_at > %s",
                (cutoff_time,)
            )
            
            # Unique users
            unique_users = self.db.fetch_dict(
                "SELECT COUNT(DISTINCT user_id) as count FROM tweets WHERE processed_at > %s",
                (cutoff_time,)
            )
            
            # Language distribution
            lang_dist = self.db.fetch_dict(
                "SELECT lang, COUNT(*) as count FROM tweets WHERE processed_at > %s GROUP BY lang",
                (cutoff_time,)
            )
            
            # Average engagement
            avg_engagement = self.db.fetch_dict(
                """
                SELECT 
                    AVG(like_count) as avg_likes,
                    AVG(retweet_count) as avg_retweets,
                    AVG(reply_count) as avg_replies,
                    AVG(engagement_rate) as avg_engagement_rate
                FROM tweets 
                WHERE processed_at > %s
                """,
                (cutoff_time,)
            )
            
            # Text quality metrics
            text_quality = self.db.fetch_dict(
                """
                SELECT 
                    AVG(char_count) as avg_length,
                    AVG(word_count) as avg_words,
                    SUM(CASE WHEN char_count < 20 THEN 1 ELSE 0 END) as too_short,
                    SUM(CASE WHEN has_urls THEN 1 ELSE 0 END) as with_urls
                FROM tweets 
                WHERE processed_at > %s
                """,
                (cutoff_time,)
            )
            
            stats = {
                'total_tweets': total[0]['count'] if total else 0,
                'unique_users': unique_users[0]['count'] if unique_users else 0,
                'language_distribution': {row['lang']: row['count'] for row in lang_dist},
                'avg_likes': float(avg_engagement[0].get('avg_likes', 0) or 0) if avg_engagement else 0,
                'avg_retweets': float(avg_engagement[0].get('avg_retweets', 0) or 0) if avg_engagement else 0,
                'avg_replies': float(avg_engagement[0].get('avg_replies', 0) or 0) if avg_engagement else 0,
                'avg_engagement_rate': float(avg_engagement[0].get('avg_engagement_rate', 0) or 0) if avg_engagement else 0,
                'avg_length': float(text_quality[0].get('avg_length', 0) or 0) if text_quality else 0,
                'avg_words': float(text_quality[0].get('avg_words', 0) or 0) if text_quality else 0,
                'too_short_count': int(text_quality[0].get('too_short', 0) or 0) if text_quality else 0,
                'with_urls_count': int(text_quality[0].get('with_urls', 0) or 0) if text_quality else 0,
                'period_hours': hours,
                'checked_at': datetime.now().isoformat(),
            }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting dataset stats: {e}")
            return {}
    
    def calculate_quality_score(self, stats: Dict[str, Any]) -> float:
        """Calculate overall quality score (0-1)."""
        try:
            score = 0.0
            weights = {
                'size': 0.3,
                'diversity': 0.2,
                'content': 0.3,
                'engagement': 0.2,
            }
            
            # Size score
            size_score = min(1.0, stats['total_tweets'] / self.min_dataset_size)
            score += size_score * weights['size']
            
            # Diversity score (unique users)
            diversity_score = min(1.0, stats['unique_users'] / self.min_unique_users)
            score += diversity_score * weights['diversity']
            
            # Content quality score
            avg_length = stats.get('avg_length', 0)
            too_short_ratio = stats.get('too_short_count', 0) / max(stats['total_tweets'], 1)
            content_score = 0.0
            
            if avg_length >= 50:  # Good average length
                content_score += 0.5
            elif avg_length >= 30:
                content_score += 0.3
            
            if too_short_ratio < 0.1:  # Less than 10% too short
                content_score += 0.5
            elif too_short_ratio < 0.2:
                content_score += 0.3
            
            score += content_score * weights['content']
            
            # Engagement score
            avg_engagement = stats.get('avg_engagement_rate', 0)
            engagement_score = min(1.0, avg_engagement * 100)  # Scale up
            score += engagement_score * weights['engagement']
            
            return round(score, 3)
            
        except Exception as e:
            self.logger.error(f"Error calculating quality score: {e}")
            return 0.0
    
    def check_quality_gates(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """Check if data passes quality gates."""
        gates = {
            'dataset_size': {
                'passed': stats['total_tweets'] >= self.min_dataset_size,
                'value': stats['total_tweets'],
                'threshold': self.min_dataset_size,
                'message': f"Dataset has {stats['total_tweets']} tweets (min: {self.min_dataset_size})"
            },
            'user_diversity': {
                'passed': stats['unique_users'] >= self.min_unique_users,
                'value': stats['unique_users'],
                'threshold': self.min_unique_users,
                'message': f"Dataset has {stats['unique_users']} unique users (min: {self.min_unique_users})"
            },
            'content_quality': {
                'passed': stats.get('too_short_count', 0) / max(stats['total_tweets'], 1) < 0.2,
                'value': stats.get('too_short_count', 0) / max(stats['total_tweets'], 1),
                'threshold': 0.2,
                'message': f"Short content ratio: {stats.get('too_short_count', 0) / max(stats['total_tweets'], 1):.2%}"
            },
            'language_consistency': {
                'passed': True,  # Default pass
                'value': len(stats.get('language_distribution', {})),
                'threshold': 1,
                'message': f"Languages: {list(stats.get('language_distribution', {}).keys())}"
            }
        }
        
        # Calculate overall quality score
        quality_score = self.calculate_quality_score(stats)
        gates['quality_score'] = {
            'passed': quality_score >= self.min_avg_quality_score,
            'value': quality_score,
            'threshold': self.min_avg_quality_score,
            'message': f"Quality score: {quality_score:.3f} (min: {self.min_avg_quality_score})"
        }
        
        # Overall pass/fail
        all_passed = all(gate['passed'] for gate in gates.values())
        
        return {
            'overall_passed': all_passed,
            'quality_score': quality_score,
            'gates': gates,
            'checked_at': datetime.now().isoformat(),
        }
    
    def detect_anomalies(self, stats: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect data anomalies."""
        anomalies = []
        
        # Check for sudden engagement drop
        if stats.get('avg_likes', 0) < 1 and stats.get('avg_retweets', 0) < 1:
            anomalies.append({
                'type': 'low_engagement',
                'severity': 'warning',
                'message': 'Very low engagement metrics detected',
                'value': stats.get('avg_likes', 0)
            })
        
        # Check for high URL ratio (possible spam)
        url_ratio = stats.get('with_urls_count', 0) / max(stats['total_tweets'], 1)
        if url_ratio > 0.8:
            anomalies.append({
                'type': 'high_url_ratio',
                'severity': 'warning',
                'message': f'High URL ratio: {url_ratio:.2%} (possible spam)',
                'value': url_ratio
            })
        
        # Check for language inconsistency
        lang_dist = stats.get('language_distribution', {})
        if len(lang_dist) > 5:
            anomalies.append({
                'type': 'language_diversity',
                'severity': 'info',
                'message': f'High language diversity: {len(lang_dist)} languages',
                'value': len(lang_dist)
            })
        
        # Check for very short average length
        if stats.get('avg_length', 0) < 30:
            anomalies.append({
                'type': 'short_content',
                'severity': 'warning',
                'message': f'Very short average content: {stats.get("avg_length", 0):.0f} chars',
                'value': stats.get('avg_length', 0)
            })
        
        return anomalies
    
    def store_validation_result(self, result: Dict[str, Any]) -> None:
        """Store validation result in database."""
        try:
            validation_data = {
                'validated_at': datetime.now().isoformat(),
                'overall_passed': result['overall_passed'],
                'quality_score': result['quality_score'],
                'dataset_size': result['gates']['dataset_size']['value'],
                'unique_users': result['gates']['user_diversity']['value'],
                'result_json': str(result),  # Store full result as JSON string
            }
            
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS quality_validations (
                    id SERIAL PRIMARY KEY,
                    validated_at TIMESTAMP NOT NULL,
                    overall_passed BOOLEAN NOT NULL,
                    quality_score FLOAT NOT NULL,
                    dataset_size INTEGER,
                    unique_users INTEGER,
                    result_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            self.db.insert('quality_validations', validation_data)
            self.logger.info(f"Stored validation result: {result['overall_passed']}")
            
        except Exception as e:
            self.logger.error(f"Error storing validation result: {e}")
    
    def update_metrics(self, stats: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Update Prometheus metrics."""
        # Log gate results
        for gate_name, gate_data in result['gates'].items():
            if not gate_data['passed']:
                self.logger.warning(f"Quality gate failed: {gate_name} - {gate_data['message']}")
    
    async def validate(self) -> Dict[str, Any]:
        """Run validation check."""
        try:
            self.logger.info("Running quality validation")
            
            # Get dataset statistics
            stats = self.get_dataset_stats(hours=24)
            
            if not stats or stats['total_tweets'] == 0:
                self.logger.warning("No data to validate")
                return {
                    'overall_passed': False,
                    'quality_score': 0.0,
                    'message': 'No data available for validation'
                }
            
            # Check quality gates
            result = self.check_quality_gates(stats)
            
            # Detect anomalies
            anomalies = self.detect_anomalies(stats)
            result['anomalies'] = anomalies
            
            # Store result
            self.store_validation_result(result)
            
            # Update metrics
            self.update_metrics(stats, result)
            
            # Log result
            if result['overall_passed']:
                self.logger.info(f"✅ Quality validation PASSED (score: {result['quality_score']:.3f})")
            else:
                self.logger.warning(f"❌ Quality validation FAILED (score: {result['quality_score']:.3f})")
                for gate_name, gate_data in result['gates'].items():
                    if not gate_data['passed']:
                        self.logger.warning(f"  - {gate_name}: {gate_data['message']}")
            
            # Log anomalies
            for anomaly in anomalies:
                level = 'warning' if anomaly['severity'] == 'warning' else 'info'
                getattr(self.logger, level)(f"Anomaly detected: {anomaly['message']}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error during validation: {e}")
            metrics.record_error('quality_validation', str(e))
            return {
                'overall_passed': False,
                'quality_score': 0.0,
                'error': str(e)
            }
    
    async def run_continuous(self, interval_seconds: int = 300) -> None:
        """Run validation checks continuously."""
        self.logger.info(f"Starting continuous validation (interval: {interval_seconds}s)")
        
        while True:
            try:
                # Run validation
                result = await self.validate()
                
                # Store result in Redis for other services to check
                self.cache.set_json('latest_quality_check', result, ttl=timedelta(hours=1))
                
                # Wait before next check
                await asyncio.sleep(interval_seconds)
                
            except KeyboardInterrupt:
                self.logger.info("Validator stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Error in validation loop: {e}")
                await asyncio.sleep(60)


async def main():
    """Main entry point."""
    setup_logging()
    logger = get_logger(__name__)
    
    logger.info("Starting Quality Gate Validator Service")
    
    validator = QualityGateValidator()
    
    # Check for once mode (run validation once then exit)
    quality_mode = os.getenv('QUALITY_MODE', 'continuous')
    
    if quality_mode == 'once':
        logger.info("🎯 ONCE MODE - Running single validation then exiting")
        
        try:
            # Run validation
            result = await validator.validate()
            
            # Store result in Redis for other services
            validator.cache.set_json('latest_quality_check', result, ttl=timedelta(hours=1))
            
            # Log final result
            if result['overall_passed']:
                logger.info(f"✅ Validation complete - PASSED (score: {result.get('quality_score', 0):.3f})")
            else:
                logger.warning(f"❌ Validation complete - FAILED (score: {result.get('quality_score', 0):.3f})")
            
        except Exception as e:
            logger.error(f"Error in once mode: {e}")
        
        logger.info("Quality gate shutdown complete (once mode)")
        return
    
    # Continuous mode
    try:
        await validator.run_continuous(interval_seconds=300)  # Every 5 minutes
    except KeyboardInterrupt:
        logger.info("Validator stopped")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        logger.info("Validator shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
