import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
import logging
from models import Article, Source

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def remove_all_articles():
    """Remove all articles and their associated sources from the database"""
    try:
        with app.app_context():
            # First log the number of articles we're about to remove
            article_count = Article.query.count()
            source_count = Source.query.count()
            logger.info(f"Found {article_count} articles and {source_count} sources to remove")

            # Delete all sources first (due to foreign key constraint)
            Source.query.delete()
            logger.info("Deleted all sources")

            # Then delete all articles
            Article.query.delete()
            logger.info("Deleted all articles")

            # Commit the transaction
            db.session.commit()
            logger.info("Successfully removed all articles and sources")

    except Exception as e:
        logger.error(f"Error removing articles: {str(e)}")
        db.session.rollback()
        raise

if __name__ == '__main__':
    remove_all_articles()
