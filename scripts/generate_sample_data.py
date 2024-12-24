import sys
import os
import logging
from datetime import datetime, timedelta
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
    return date - timedelta(days=date.weekday())

def get_sunday_of_week(date):
    """Get the Sunday of the week (end of week) for a given date"""
    monday = get_monday_of_week(date)
    return monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

def generate_sample_articles():
    """Generate sample articles if they don't exist"""
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

        # Generate articles for past 4 weeks from today
        current_date = datetime.utcnow()
        weeks = []

        # Get the most recent Monday
        last_monday = get_monday_of_week(current_date)

        # Generate dates for the last 4 weeks
        for i in range(4):
            week_date = last_monday - timedelta(weeks=i)
            weeks.append(week_date)
            logger.info(f"Added week starting {week_date.strftime('%Y-%m-%d')} to generation queue")

        success_count = 0

        with app.app_context():
            for monday in weeks:
                try:
                    logger.info(f"=== Generating article for week {monday.strftime('%Y-%m-%d')} ===")

                    # Add delay between article generations to handle rate limits
                    if success_count > 0:
                        delay = 30  # 30 seconds between generations
                        logger.info(f"Waiting {delay} seconds before generating next article...")
                        import time
                        time.sleep(delay)

                    # Generate article
                    article = content_service.generate_weekly_summary(github_content, monday)

                    if article:
                        success_count += 1
                        logger.info(f"Generated article for week of {monday.strftime('%Y-%m-%d')}: {article.title}")

                except Exception as e:
                    logger.error(f"Error generating article for week of {monday.strftime('%Y-%m-%d')}: {str(e)}")
                    db.session.rollback()
                    continue

        logger.info(f"=== Sample Data Generation Complete ===")
        logger.info(f"Successfully generated {success_count} articles")
        return success_count > 0

    except Exception as e:
        logger.error(f"Fatal error in sample data generation: {str(e)}")
        return False

if __name__ == "__main__":
    print("\n=== Starting Sample Data Generation Script ===\n")
    success = generate_sample_articles()
    exit_code = 0 if success else 1
    print(f"\n=== Sample Data Generation {'Succeeded' if success else 'Failed'} ===\n")
    sys.exit(exit_code)