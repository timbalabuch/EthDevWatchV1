import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import Article
from services.forum_service import ForumService
import logging

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def update_forum_summaries(force_update=True):
    """Update forum summaries for articles."""
    try:
        with app.app_context():
            # Get all articles if force_update is True, otherwise only those without summaries
            if force_update:
                articles = Article.query.order_by(Article.publication_date.desc()).all()
            else:
                articles = Article.query.filter(Article.forum_summary.is_(None)).all()

            logger.info(f"Found {len(articles)} articles to process")

            if not articles:
                logger.info("No articles found needing forum summaries")
                return

            forum_service = ForumService()

            for article in articles:
                logger.info(f"Processing article from {article.publication_date}")
                try:
                    # Get forum summary for the week
                    summary = forum_service.get_weekly_forum_summary(article.publication_date)

                    if summary:
                        article.forum_summary = summary
                        logger.info(f"Successfully added forum summary for article dated {article.publication_date}")
                    else:
                        logger.warning(f"No forum summary generated for article dated {article.publication_date}")

                except Exception as e:
                    logger.error(f"Error processing article {article.id}: {str(e)}")
                    continue

            # Commit all changes
            db.session.commit()
            logger.info("Successfully updated forum summaries")

    except Exception as e:
        logger.error(f"Error updating forum summaries: {str(e)}")
        raise

if __name__ == '__main__':
    logger.info("Starting forum summaries update")
    update_forum_summaries(force_update=True)