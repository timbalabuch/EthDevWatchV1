import sys
import os
import logging
from datetime import datetime, timedelta
import pytz

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import Article, WeeklyMetrics
from services.dune_service import DuneService

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def update_article_metrics():
    """Update metrics for all existing articles"""
    try:
        with app.app_context():
            dune_service = DuneService()
            articles = Article.query.order_by(Article.publication_date.desc()).all()
            
            if not articles:
                logger.info("No articles found to update metrics")
                return True
            
            logger.info(f"Found {len(articles)} articles to update metrics")
            
            success_count = 0
            for article in articles:
                try:
                    # Get the week's date range for the article
                    start_date = article.publication_date
                    if start_date.tzinfo is None:
                        start_date = pytz.UTC.localize(start_date)

                    # Calculate end date (Sunday of the same week)
                    end_date = start_date + timedelta(days=6, hours=23, minutes=59, seconds=59)
                    
                    logger.info(f"Updating metrics for article from {start_date.strftime('%Y-%m-%d')}")
                    
                    # Delete existing metrics if any
                    if article.metrics:
                        logger.info(f"Deleting existing metrics for article {article.id}")
                        db.session.delete(article.metrics)
                        db.session.commit()

                    # Fetch new metrics from Dune
                    metrics_data = dune_service.get_weekly_metrics(
                        start_date=start_date,
                        end_date=end_date
                    )

                    if not metrics_data:
                        logger.warning(f"No metrics data available for week of {start_date.strftime('%Y-%m-%d')}")
                        continue

                    # Create new metrics
                    metrics = WeeklyMetrics(
                        article=article,
                        active_addresses=metrics_data.get('active_addresses'),
                        contracts_deployed=metrics_data.get('contracts_deployed'),
                        eth_burned=metrics_data.get('eth_burned'),
                        start_date=start_date,
                        end_date=end_date
                    )

                    db.session.add(metrics)
                    db.session.commit()
                    
                    success_count += 1
                    logger.info(f"Successfully updated metrics for article {success_count}/{len(articles)}")
                    
                    # Add delay between updates to handle rate limits
                    if success_count < len(articles):
                        delay = 30  # 30 seconds between updates
                        logger.info(f"Waiting {delay} seconds before next update...")
                        import time
                        time.sleep(delay)
                        
                except Exception as e:
                    logger.error(f"Error updating metrics for article: {str(e)}")
                    db.session.rollback()
                    continue
            
            logger.info(f"Metrics update complete. Successfully updated {success_count}/{len(articles)} articles")
            return success_count > 0
            
    except Exception as e:
        logger.error(f"Fatal error in metrics update: {str(e)}")
        return False

if __name__ == "__main__":
    print("\n=== Starting Metrics Update ===\n")
    success = update_article_metrics()
    exit_code = 0 if success else 1
    print(f"\n=== Metrics Update {'Succeeded' if success else 'Failed'} ===\n")
    sys.exit(exit_code)
