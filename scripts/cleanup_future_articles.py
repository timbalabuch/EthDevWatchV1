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

def cleanup_future_articles():
    """Remove any articles with publication dates in the future"""
    try:
        with app.app_context():
            # Get current UTC time with timezone information
            current_date = datetime.now(pytz.UTC)
            logger.info(f"Current UTC time: {current_date}")

            # Find any articles with publication dates in the future
            future_articles = Article.query.filter(
                Article.publication_date >= current_date
            ).all()

            if not future_articles:
                logger.info("No future articles found")
                return True

            logger.info(f"Found {len(future_articles)} articles with future dates")

            # Delete future articles and their associated sources
            for article in future_articles:
                logger.info(f"Removing article dated {article.publication_date}: {article.title}")
                # Delete sources first
                Source.query.filter_by(article_id=article.id).delete()
                # Then delete the article
                db.session.delete(article)

            db.session.commit()
            logger.info("Successfully removed all future articles")
            return True

    except Exception as e:
        logger.error(f"Error cleaning up future articles: {str(e)}")
        db.session.rollback()
        return False

if __name__ == '__main__':
    success = cleanup_future_articles()
    exit_code = 0 if success else 1
    sys.exit(exit_code)