import sys
import os
import logging
from datetime import datetime, timedelta
import pytz
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import Article, Source

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def cleanup_articles():
    """Clean up articles with incorrect dates and duplicates"""
    try:
        with app.app_context():
            # Get current UTC time
            current_date = datetime.now(pytz.UTC)
            current_date = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Calculate current week's Monday
            days_since_monday = current_date.weekday()
            current_monday = current_date - timedelta(days=days_since_monday)
            
            logger.info(f"Cleaning up articles...")

            # Step 1: Remove articles from current and future weeks
            future_articles = Article.query.filter(
                Article.publication_date >= current_monday
            ).all()
            
            if future_articles:
                logger.info(f"Found {len(future_articles)} articles to remove")
                for article in future_articles:
                    # Delete associated sources first
                    Source.query.filter_by(article_id=article.id).delete()
                    db.session.delete(article)
                db.session.commit()
                logger.info("Removed articles from current and future weeks")

            # Step 2: Fix any incorrect dates and remove duplicates
            all_articles = Article.query.order_by(Article.publication_date).all()
            seen_weeks = set()
            articles_to_delete = []

            for article in all_articles:
                # Get Monday of the article's week
                article_date = article.publication_date.replace(hour=0, minute=0, second=0, microsecond=0)
                week_monday = article_date - timedelta(days=article_date.weekday())
                
                # Check for duplicates
                week_key = week_monday.strftime('%Y-%m-%d')
                if week_key in seen_weeks:
                    logger.info(f"Found duplicate article for week of {week_key}")
                    articles_to_delete.append(article)
                else:
                    seen_weeks.add(week_key)
                    # Ensure publication date is set to Monday
                    if article.publication_date.weekday() != 0:
                        article.publication_date = week_monday
            
            # Delete duplicates
            if articles_to_delete:
                logger.info(f"Removing {len(articles_to_delete)} duplicate articles")
                for article in articles_to_delete:
                    Source.query.filter_by(article_id=article.id).delete()
                    db.session.delete(article)
            
            db.session.commit()
            logger.info("Cleanup completed successfully")
            return True

    except Exception as e:
        logger.error(f"Error cleaning up articles: {str(e)}")
        db.session.rollback()
        return False

if __name__ == '__main__':
    success = cleanup_articles()
    sys.exit(0 if success else 1)
