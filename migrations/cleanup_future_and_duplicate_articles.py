import sys
import os
import logging
from datetime import datetime
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
            logger.info(f"Starting cleanup of articles...")

            # Get all articles ordered by publication date
            articles = Article.query.order_by(Article.publication_date.asc()).all()
            seen_weeks = {}
            articles_to_delete = []

            for article in articles:
                # Skip if article has no date range (shouldn't happen but let's be safe)
                if not article.date_range:
                    continue

                week_start, week_end = article.date_range

                # Check for future dates
                if week_end > current_date:
                    logger.info(f"Found article with future dates: {article.title}, end date: {week_end}")
                    articles_to_delete.append(article)
                    continue

                # Group articles by week start date
                week_key = week_start.strftime('%Y-%m-%d')
                if week_key in seen_weeks:
                    # If we already have an article for this week, keep the newest one
                    existing_article = seen_weeks[week_key]
                    if article.publication_date > existing_article.publication_date:
                        articles_to_delete.append(existing_article)
                        seen_weeks[week_key] = article
                    else:
                        articles_to_delete.append(article)
                    logger.info(f"Found duplicate article for week of {week_key}")
                else:
                    seen_weeks[week_key] = article

            # Delete problematic articles
            if articles_to_delete:
                logger.info(f"Removing {len(articles_to_delete)} problematic articles")
                for article in articles_to_delete:
                    logger.info(f"Deleting article: {article.title} (week of {article.formatted_date_range})")
                    db.session.delete(article)
                db.session.commit()
                logger.info("Articles removed successfully")
            else:
                logger.info("No problematic articles found")

            return True

    except Exception as e:
        logger.error(f"Error cleaning up articles: {str(e)}")
        db.session.rollback()
        return False

if __name__ == '__main__':
    success = cleanup_articles()
    sys.exit(0 if success else 1)