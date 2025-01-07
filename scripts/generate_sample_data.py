import sys
import os
import logging
from datetime import datetime, timedelta
import pytz # Added import for timezone support

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

def get_missing_weeks():
    """Get a list of weeks that don't have articles"""
    with app.app_context():
        current_date = datetime.utcnow()
        current_date = pytz.UTC.localize(current_date)
        last_monday = get_monday_of_week(current_date)
        missing_weeks = []

        # Check last 4 weeks
        for i in range(4):
            week_start = last_monday - timedelta(weeks=i)
            week_end = get_sunday_of_week(week_start)

            # Check if article exists for this week
            existing = Article.query.filter(
                Article.publication_date >= week_start,
                Article.publication_date <= week_end
            ).first()

            if not existing:
                missing_weeks.append(week_start)
                logger.info(f"No article found for week of {week_start.strftime('%Y-%m-%d')}")
            else:
                logger.info(f"Article exists for week of {week_start.strftime('%Y-%m-%d')}: {existing.title}")

        return missing_weeks

def generate_sample_articles():
    """Generate articles for missing weeks"""
    try:
        # Check if we're in production environment
        is_production = os.environ.get('REPL_ENVIRONMENT') == 'production'
        if is_production:
            logger.error("Cannot generate sample articles in production environment")
            return False

        logger.info("=== Starting Sample Data Generation ===")
        logger.info("Running in development environment - proceeding with sample data generation")

        # Find which weeks need articles
        missing_weeks = get_missing_weeks()

        if not missing_weeks:
            logger.info("No missing articles - all weeks are covered")
            return True

        logger.info(f"Found {len(missing_weeks)} weeks needing articles")

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

        success_count = 0

        with app.app_context():
            for monday in missing_weeks:
                try:
                    logger.info(f"=== Generating article for week {monday.strftime('%Y-%m-%d')} ===")

                    # Add delay between article generations
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
    # Check environment before running
    is_production = os.environ.get('REPL_ENVIRONMENT') == 'production'
    if is_production:
        logger.error("This script cannot be run in production environment")
        sys.exit(1)

    print("\n=== Starting Sample Data Generation Script ===\n")
    success = generate_sample_articles()
    exit_code = 0 if success else 1
    print(f"\n=== Sample Data Generation {'Succeeded' if success else 'Failed'} ===\n")
    sys.exit(exit_code)