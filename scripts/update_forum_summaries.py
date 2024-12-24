import sys
import os
import time
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

def update_forum_summaries():
    """Update forum summaries for articles."""
    try:
        with app.app_context():
            # Get articles ordered by date, focusing on recent ones first
            articles = Article.query.order_by(Article.publication_date.desc()).all()
            total_articles = len(articles)
            logger.info(f"Found {total_articles} articles to process")

            if not articles:
                logger.info("No articles found needing forum summaries")
                return

            forum_service = ForumService()

            for index, article in enumerate(articles, 1):
                start_time = time.time()
                logger.info(f"Processing article {index}/{total_articles} ({(index/total_articles)*100:.1f}%) from {article.publication_date}")

                try:
                    # Get forum summary for the week
                    logger.info(f"Fetching forum discussions for article dated {article.publication_date}")
                    summary = forum_service.get_weekly_forum_summary(article.publication_date)

                    if summary:
                        article.forum_summary = summary
                        db.session.commit()  # Commit after each successful update
                        process_time = time.time() - start_time
                        logger.info(f"Successfully added forum summary for article dated {article.publication_date} in {process_time:.2f} seconds")
                        # Add a larger delay between articles to avoid rate limits
                        delay = 5  # Increased delay between articles
                        logger.info(f"Waiting {delay} seconds before processing next article...")
                        time.sleep(delay)
                    else:
                        logger.warning(f"No forum summary generated for article dated {article.publication_date}")
                        time.sleep(2)  # Small delay even for failed attempts

                except Exception as e:
                    logger.error(f"Error processing article {article.id}: {str(e)}")
                    db.session.rollback()
                    # Add a longer delay after errors
                    error_delay = 10  # Increased delay after errors
                    logger.info(f"Error occurred, waiting {error_delay} seconds before continuing...")
                    time.sleep(error_delay)
                    continue

            logger.info("Successfully completed forum summaries update")

    except Exception as e:
        logger.error(f"Error updating forum summaries: {str(e)}")
        raise

if __name__ == '__main__':
    logger.info("Starting forum summaries update")
    update_forum_summaries()