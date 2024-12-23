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

def get_sunday_of_week(date):
    """Get the Sunday of the week (end of week) for a given date"""
    monday = get_monday_of_week(date)
    return monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

def get_weeks_in_range(start_date, end_date):
    """Get all Mondays between start_date and end_date"""
    current = get_monday_of_week(start_date)
    weeks = []
    while current <= end_date:
        weeks.append(current)
        current += timedelta(days=7)
    return weeks

def generate_sample_articles():
    """Generate sample articles up to current date"""
    try:
        logger.info("=== Starting Sample Data Generation ===")
        logger.info("Initializing services...")
        github_service = GitHubService()
        content_service = ContentService()

        # Get real GitHub content for reference
        logger.info("Fetching GitHub content...")
        github_content = github_service.fetch_recent_content()

        if not github_content:
            logger.error("No content fetched from GitHub. Cannot generate sample articles.")
            return False

        logger.info(f"Successfully fetched {len(github_content)} items from GitHub")

        # Clean up existing data
        cleanup_existing_data()

        # Calculate all weeks up to current date
        start_date = datetime(2024, 11, 1)
        current_date = datetime.utcnow()

        # Get all Monday dates up to current date
        weeks = get_weeks_in_range(start_date, current_date)

        # Generate articles for each completed week
        success_count = 0
        with app.app_context():
            for monday in weeks:
                try:
                    # Calculate the end of the week (Sunday at 23:59:59)
                    week_end = get_sunday_of_week(monday)

                    # Skip if week hasn't ended yet
                    if week_end > current_date:
                        logger.info(f"Skipping incomplete week: {monday.strftime('%Y-%m-%d')} - {week_end.strftime('%Y-%m-%d')}")
                        continue

                    logger.info(f"=== Generating article for week {monday.strftime('%Y-%m-%d')} - {week_end.strftime('%Y-%m-%d')} ===")
                    article = content_service.generate_weekly_summary(github_content, monday)

                    # Set the publication date to the end of the week
                    article.publication_date = week_end
                    db.session.commit()

                    success_count += 1
                    logger.info(f"Generated article for week of {monday.strftime('%Y-%m-%d')}: {article.title}")

                except Exception as e:
                    logger.error(f"Error generating article for week of {monday.strftime('%Y-%m-%d')}: {str(e)}")
                    db.session.rollback()
                    continue

        total_weeks = len([w for w in weeks if get_sunday_of_week(w) <= current_date])
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