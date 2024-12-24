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

def get_monday_of_week(date):
    """Get the Monday of the week for a given date"""
    return date - timedelta(days=date.weekday())

def get_sunday_of_week(date):
    """Get the Sunday of the week (end of week) for a given date"""
    monday = get_monday_of_week(date)
    return monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

def check_existing_articles():
    """Check if we already have articles generated"""
    try:
        with app.app_context():
            article_count = Article.query.count()
            logger.info(f"Found {article_count} existing articles")
            return article_count > 0
    except Exception as e:
        logger.error(f"Error checking existing articles: {str(e)}")
        return False

def generate_sample_articles():
    """Generate sample articles if they don't exist"""
    try:
        logger.info("=== Starting Sample Data Generation ===")

        # Check if articles already exist
        if check_existing_articles():
            logger.info("Articles already exist, skipping generation")
            return True

        # Initialize services
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

        # Start with just last 2 weeks for initial generation
        start_date = datetime.utcnow() - timedelta(days=14)
        current_date = datetime.utcnow()

        # Get all Monday dates
        weeks = []
        current = get_monday_of_week(start_date)
        while current <= current_date:
            weeks.append(current)
            current += timedelta(days=7)

        # Generate articles for each completed week
        success_count = 0
        image_url = None  # Store the first generated image URL for reuse

        with app.app_context():
            for monday in weeks:
                try:
                    # Calculate the end of the week
                    week_end = get_sunday_of_week(monday)

                    # Skip if week hasn't ended yet
                    if week_end > current_date:
                        logger.info(f"Skipping incomplete week: {monday.strftime('%Y-%m-%d')}")
                        continue

                    logger.info(f"=== Generating article for week {monday.strftime('%Y-%m-%d')} ===")

                    # Add significant delay between article generations
                    if success_count > 0:
                        delay = 30  # 30 seconds between generations
                        logger.info(f"Waiting {delay} seconds before generating next article...")
                        import time
                        time.sleep(delay)

                    # Generate article with the stored image URL
                    article = content_service.generate_weekly_summary(github_content, monday)

                    # If this is the first successful article, store its image URL
                    if success_count == 0 and article and article.image_url:
                        image_url = article.image_url
                    elif image_url and article:
                        # Reuse the stored image URL for subsequent articles
                        article.image_url = image_url
                        db.session.commit()

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