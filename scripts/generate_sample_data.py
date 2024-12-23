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

def generate_sample_articles():
    """Generate sample articles for the past 5 weeks"""
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

        # Generate articles for past weeks
        success_count = 0
        with app.app_context():
            # Start from 4 weeks ago (to generate 5 weeks including current week)
            current_date = datetime.utcnow()
            for weeks_ago in range(4, -1, -1):
                try:
                    # Calculate the Monday of each week
                    week_date = current_date - timedelta(weeks=weeks_ago)
                    monday = get_monday_of_week(week_date)
                    publication_date = monday.replace(hour=0, minute=0, second=0, microsecond=0)

                    logger.info(f"=== Generating article for week starting {publication_date.strftime('%Y-%m-%d')} ===")
                    article = content_service.generate_weekly_summary(github_content)

                    # Set the publication date for the article
                    article.publication_date = publication_date
                    db.session.commit()

                    success_count += 1
                    logger.info(f"Generated article for week {weeks_ago+1}: {article.title}")

                except Exception as e:
                    logger.error(f"Error generating article for week {weeks_ago+1}: {str(e)}")
                    db.session.rollback()
                    continue

        logger.info(f"=== Sample Data Generation Complete ===")
        logger.info(f"Successfully generated {success_count} out of 5 articles.")
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