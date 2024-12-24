import sys
import os
import logging
from datetime import datetime, timedelta
import pytz
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import Article

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_last_completed_week():
    """Get the date range for the last completed week"""
    current_date = datetime.now(pytz.UTC)

    # Calculate the last completed Sunday
    days_since_sunday = current_date.weekday() + 1  # +1 because we want the previous Sunday
    last_sunday = current_date - timedelta(days=days_since_sunday)
    last_sunday = last_sunday.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Get the Monday of that week
    last_monday = last_sunday - timedelta(days=6)
    last_monday = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)

    return last_monday, last_sunday

def cleanup_future_articles():
    """Remove any articles that are not from completed weeks"""
    try:
        with app.app_context():
            # Get current UTC time with timezone information
            current_date = datetime.now(pytz.UTC)
            logger.info(f"Current UTC time: {current_date}")

            # Get the last completed week's date range
            last_monday, last_sunday = get_last_completed_week()
            logger.info(f"Last completed week: {last_monday.strftime('%Y-%m-%d')} to {last_sunday.strftime('%Y-%m-%d')}")

            # Find articles after the last completed Sunday
            future_articles = Article.query.filter(
                Article.publication_date > last_sunday
            ).all()

            if not future_articles:
                logger.info("No future articles found")
                return True

            # Log the articles that will be removed
            logger.info(f"Found {len(future_articles)} articles with future dates")
            for article in future_articles:
                logger.info(f"Removing article: {article.title} (Date: {article.publication_date})")
                # Delete the article and its associated sources (cascade delete)
                db.session.delete(article)

            db.session.commit()
            logger.info("Successfully removed all future articles")
            return True

    except Exception as e:
        logger.error(f"Error cleaning up future articles: {str(e)}")
        db.session.rollback()
        return False

if __name__ == "__main__":
    success = cleanup_future_articles()
    exit_code = 0 if success else 1
    sys.exit(exit_code)