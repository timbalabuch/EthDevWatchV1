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

def cleanup_articles():
    """Clean up articles with future dates in their range and remove duplicates"""
    try:
        with app.app_context():
            current_date = datetime.now(pytz.UTC)
            logger.info(f"Current UTC time: {current_date}")

            # Calculate the start of next Monday for future date comparison
            days_until_monday = (7 - current_date.weekday()) % 7
            next_monday = current_date.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_until_monday)
            logger.info(f"Next Monday starts at: {next_monday}")

            # Get all articles ordered by publication date
            articles = Article.query.order_by(Article.publication_date.asc()).all()
            week_ranges = {}  # Store articles by their week range
            articles_to_delete = []

            for article in articles:
                if not article.date_range:
                    logger.warning(f"Article {article.id} has no date range, skipping")
                    continue

                week_start, week_end = article.date_range

                # Add debug logging for date comparisons
                logger.debug(f"Article {article.id}: Start {week_start}, End {week_end}, Current {current_date}")

                # Check for future dates
                if week_end > current_date:
                    logger.info(f"Found article with future dates: {article.title}, end date: {week_end}")
                    articles_to_delete.append(article)
                    continue

                # Check if article starts on a Monday
                if week_start.weekday() != 0:
                    logger.info(f"Found article not starting on Monday: {article.title}, start date: {week_start}")
                    articles_to_delete.append(article)
                    continue

                # Get standardized week range key (Monday 00:00:00 to Sunday 23:59:59)
                week_key = week_start.strftime('%Y-%m-%d')

                # If we already have an article for this week
                if week_key in week_ranges:
                    existing_article = week_ranges[week_key]
                    # Keep the newer article
                    if article.publication_date > existing_article.publication_date:
                        logger.info(f"Found newer article for week {week_key}, marking older article for deletion")
                        articles_to_delete.append(existing_article)
                        week_ranges[week_key] = article
                    else:
                        logger.info(f"Found duplicate article for week {week_key}, marking newer article for deletion")
                        articles_to_delete.append(article)
                else:
                    week_ranges[week_key] = article

            # Delete problematic articles
            if articles_to_delete:
                logger.info(f"Removing {len(articles_to_delete)} problematic articles")
                for article in articles_to_delete:
                    logger.info(f"Deleting article: {article.title} (week of {article.formatted_date_range})")
                    db.session.delete(article)
                db.session.commit()
                logger.info("Articles removed successfully")
            else:
                logger.info("No future articles found")

            return True

    except Exception as e:
        logger.error(f"Error cleaning up articles: {str(e)}")
        db.session.rollback()
        return False

if __name__ == '__main__':
    success = cleanup_articles()
    sys.exit(0 if success else 1)