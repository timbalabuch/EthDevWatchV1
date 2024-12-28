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

def generate_article_for_date(target_date=None):
    """Generate an article for a specific date or the current week"""
    try:
        logger.info("=== Starting Article Generation ===")

        # Initialize services
        logger.info("Initializing services...")
        github_service = GitHubService()
        content_service = ContentService()

        current_date = datetime.now(pytz.UTC)

        # Only allow article generation on Mondays
        if current_date.weekday() != 0 and not target_date:
            logger.warning("Articles can only be generated on Mondays")
            return False

        # Calculate the appropriate Monday
        if target_date:
            if not target_date.tzinfo:
                target_date = pytz.UTC.localize(target_date)
            monday = target_date - timedelta(days=target_date.weekday())
        else:
            # For current week, use the previous Monday
            days_since_monday = current_date.weekday()
            monday = current_date - timedelta(days=days_since_monday)

        monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)

        # Prevent article generation for future weeks
        if monday >= current_date.replace(hour=0, minute=0, second=0, microsecond=0):
            logger.warning(f"Cannot create article for future week of {monday.strftime('%Y-%m-%d')}")
            return False

        with app.app_context():
            try:
                logger.info(f"Generating article for week of {monday.strftime('%Y-%m-%d')}")

                # Check if article already exists for this week
                existing_article = Article.query.filter(
                    Article.publication_date >= monday,
                    Article.publication_date < monday + timedelta(days=7)
                ).first()

                if existing_article:
                    logger.warning(f"Article already exists for week of {monday.strftime('%Y-%m-%d')}")
                    return False

                # Get GitHub content
                logger.info("Fetching GitHub content...")
                github_content = github_service.fetch_recent_content()

                if not github_content:
                    logger.error("No content fetched from GitHub")
                    return False

                logger.info(f"Successfully fetched {len(github_content)} items from GitHub")

                # Generate the article with the correct Monday date
                article = content_service.generate_weekly_summary(github_content, monday)

                if article:
                    logger.info(f"Successfully generated article: {article.title}")
                    return True
                else:
                    logger.error("Failed to generate article")
                    return False

            except Exception as e:
                logger.error(f"Error generating article: {str(e)}")
                db.session.rollback()
                return False

    except Exception as e:
        logger.error(f"Fatal error in article generation: {str(e)}")
        return False

if __name__ == "__main__":
    # If a date is provided as argument, use it
    target_date = None
    if len(sys.argv) > 1:
        try:
            target_date = datetime.strptime(sys.argv[1], '%Y-%m-%d')
            print(f"\n=== Generating Article for week of {target_date.strftime('%Y-%m-%d')} ===\n")
        except ValueError as e:
            print(f"Error parsing date: {e}")
            sys.exit(1)

    success = generate_article_for_date(target_date)
    exit_code = 0 if success else 1
    print(f"\n=== Article Generation {'Succeeded' if success else 'Failed'} ===\n")
    sys.exit(exit_code)