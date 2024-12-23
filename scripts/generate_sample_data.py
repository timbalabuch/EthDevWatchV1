import sys
import os
import logging
from datetime import datetime, timedelta
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from services.github_service import GitHubService
from services.content_service import ContentService
from models import Article, Source

# Setup logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def cleanup_existing_data():
    """Remove existing articles and sources"""
    try:
        with app.app_context():
            # First delete sources due to foreign key constraint
            Source.query.delete()
            Article.query.delete()
            db.session.commit()
            logger.info("Cleaned up existing articles and sources")
    except Exception as e:
        logger.error(f"Error cleaning up data: {str(e)}")
        db.session.rollback()
        raise

def get_monday_of_week(date):
    """Get the Monday of the week for a given date"""
    return date - timedelta(days=date.weekday())

def get_weeks_in_range(start_date, end_date):
    """Get all Mondays between start_date and end_date"""
    current = get_monday_of_week(start_date)
    weeks = []
    while current <= end_date:
        weeks.append(current)
        current += timedelta(days=7)
    return weeks

def generate_sample_articles():
    """Generate sample articles for November and December 2024"""
    try:
        logger.info("=== Starting Sample Data Generation ===")
        logger.info("Initializing services...")
        github_service = GitHubService()
        content_service = ContentService()

        # Get real GitHub content
        logger.info("Fetching GitHub content...")
        github_content = github_service.fetch_recent_content()

        if not github_content:
            logger.error("No content fetched from GitHub. Cannot generate sample articles.")
            return False

        logger.info(f"Successfully fetched {len(github_content)} items from GitHub")

        # Clean up existing data
        cleanup_existing_data()

        # Calculate all weeks in November and December 2024
        start_date = datetime(2024, 11, 1)
        end_date = datetime(2024, 12, 31)
        weeks = get_weeks_in_range(start_date, end_date)

        # Generate articles for each week
        success_count = 0
        with app.app_context():
            for monday in weeks:
                try:
                    publication_date = monday.replace(hour=0, minute=0, second=0, microsecond=0)

                    logger.info(f"=== Generating article for week starting {publication_date.strftime('%Y-%m-%d')} ===")
                    article = content_service.generate_weekly_summary(github_content)

                    # Set the publication date for the article
                    article.publication_date = publication_date
                    db.session.commit()

                    success_count += 1
                    logger.info(f"Generated article for week of {publication_date.strftime('%Y-%m-%d')}: {article.title}")

                except Exception as e:
                    logger.error(f"Error generating article for week of {publication_date.strftime('%Y-%m-%d')}: {str(e)}")
                    db.session.rollback()
                    continue

        total_weeks = len(weeks)
        logger.info(f"=== Sample Data Generation Complete ===")
        logger.info(f"Successfully generated {success_count} out of {total_weeks} articles.")
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