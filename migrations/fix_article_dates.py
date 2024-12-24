import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import Article
from datetime import datetime, timedelta
import pytz
import logging

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def fix_article_dates():
    """Fix article dates to properly reflect their weekly periods"""
    with app.app_context():
        try:
            # Get all articles ordered by their original dates
            articles = Article.query.order_by(Article.publication_date.desc()).all()

            if not articles:
                logger.info("No articles found to fix")
                return

            for article in articles:
                # Ensure the date is timezone-aware
                if article.publication_date.tzinfo is None:
                    # Get the Monday of the week for this article
                    monday = article.publication_date - timedelta(days=article.publication_date.weekday())
                    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
                    monday = pytz.UTC.localize(monday)

                    logger.info(f"Updating article '{article.title}' date from {article.publication_date} to {monday}")
                    article.publication_date = monday

            # Commit all changes
            try:
                db.session.commit()
                logger.info("Successfully updated article dates")
            except Exception as e:
                logger.error(f"Error committing changes: {str(e)}")
                db.session.rollback()
                raise

        except Exception as e:
            logger.error(f"Error updating article dates: {str(e)}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    fix_article_dates()