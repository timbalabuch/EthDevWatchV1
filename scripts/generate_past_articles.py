import sys
import os
import logging
from datetime import datetime, timedelta
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from scripts.generate_one_article import generate_article_for_date
from models import Article

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def wait_for_generating_articles():
    """Wait until there are no articles in generating status."""
    while True:
        with app.app_context():
            generating = Article.query.filter_by(status='generating').first()
            if not generating:
                return
            logger.info("Waiting for article to finish generating...")
            time.sleep(5)  # Wait for 5 seconds before checking again

def generate_past_articles(num_articles=10):
    """Generate specified number of past articles"""
    try:
        logger.info(f"=== Starting Generation of {num_articles} Past Articles ===")

        # Calculate current Monday
        current_date = datetime.utcnow()
        current_monday = current_date - timedelta(days=current_date.weekday())
        current_monday = current_monday.replace(hour=0, minute=0, second=0, microsecond=0)

        success_count = 0

        # Generate articles for past weeks
        for i in range(1, num_articles + 1):
            # Wait for any currently generating articles to complete
            wait_for_generating_articles()

            target_date = current_monday - timedelta(weeks=i)
            logger.info(f"Generating article for week of {target_date.strftime('%Y-%m-%d')}")

            if generate_article_for_date(target_date):
                success_count += 1
                logger.info(f"Successfully generated article {success_count} of {num_articles}")
            else:
                logger.warning(f"Failed to generate article for week of {target_date.strftime('%Y-%m-%d')}")

        logger.info(f"=== Completed Generation of Past Articles ===")
        logger.info(f"Successfully generated {success_count} out of {num_articles} articles")
        return success_count

    except Exception as e:
        logger.error(f"Fatal error generating past articles: {str(e)}")
        return 0

if __name__ == "__main__":
    success_count = generate_past_articles()
    exit_code = 0 if success_count > 0 else 1
    sys.exit(exit_code)