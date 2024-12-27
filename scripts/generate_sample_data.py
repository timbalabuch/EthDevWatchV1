import sys
import os
import logging
from datetime import datetime, timedelta
import pytz

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from services.github_service import GitHubService
from services.content_service import ContentService
from models import Article, Source

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def get_monday_of_week(date):
    """Get the Monday of the week for a given date"""
    monday = date - timedelta(days=date.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)

def get_sunday_of_week(date):
    """Get the Sunday of the week (end of week) for a given date"""
    monday = get_monday_of_week(date)
    return monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

def generate_sample_articles():
    """Generate articles for current week"""
    try:
        logger.info("=== Starting Sample Data Generation ===")

        # Initialize services
        logger.info("Initializing services...")
        github_service = GitHubService()
        content_service = ContentService()

        # Get real GitHub content
        logger.info("Fetching GitHub content...")
        github_content = github_service.fetch_recent_content()

        if not github_content:
            logger.error("No content fetched from GitHub")
            return False

        logger.info(f"Successfully fetched {len(github_content)} items from GitHub")

        current_date = datetime.now(pytz.UTC)
        monday = get_monday_of_week(current_date)

        with app.app_context():
            try:
                logger.info(f"=== Generating article for week {monday.strftime('%Y-%m-%d')} ===")

                # Generate article
                article = content_service.generate_weekly_summary(github_content, monday)

                if article:
                    logger.info(f"Successfully generated article: {article.title}")
                    return True
                else:
                    logger.error("Failed to generate article")
                    return False

            except Exception as e:
                logger.error(f"Error generating article: {str(e)}", exc_info=True)
                db.session.rollback()
                return False

    except Exception as e:
        logger.error(f"Fatal error in sample data generation: {str(e)}", exc_info=True)
        return False

if __name__ == "__main__":
    print("\n=== Starting Sample Data Generation Script ===\n")
    success = generate_sample_articles()
    exit_code = 0 if success else 1
    print(f"\n=== Sample Data Generation {'Succeeded' if success else 'Failed'} ===\n")
    sys.exit(exit_code)