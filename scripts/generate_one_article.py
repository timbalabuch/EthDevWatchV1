import sys
import os
import logging
import argparse
from datetime import datetime, timedelta
import pytz
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from services.github_service import GitHubService
from services.content_service import ContentService
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

def get_next_monday(dt):
    """Get the next Monday from a given date."""
    days_until_monday = (7 - dt.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    return dt + timedelta(days=days_until_monday)

def generate_article_for_date(target_date=None):
    """Generate an article for a specific date or the current week"""
    try:
        logger.info("=== Starting Article Generation ===")

        # Initialize services
        logger.info("Initializing services...")
        github_service = GitHubService()
        content_service = ContentService()

        current_date = datetime.now(pytz.UTC)
        current_date = current_date.replace(hour=0, minute=0, second=0, microsecond=0)

        # Handle target date
        if target_date:
            if not target_date.tzinfo:
                target_date = pytz.UTC.localize(target_date)
            target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            monday = target_date - timedelta(days=target_date.weekday())
        else:
            # For current date, get the previous week's Monday
            days_since_monday = current_date.weekday()
            monday = current_date - timedelta(days=days_since_monday + 7)

        monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        next_monday = get_next_monday(monday)

        # Validate article date
        if monday >= current_date:
            logger.warning(f"Cannot create article for current or future week: {monday.strftime('%Y-%m-%d')}")
            return False

        # Ensure the current date is at least on the next Monday for the target week
        required_monday = get_next_monday(monday)
        if current_date < required_monday:
            logger.warning(f"Cannot create article until {required_monday.strftime('%Y-%m-%d')}")
            return False

        with app.app_context():
            try:
                logger.info(f"Generating article for week of {monday.strftime('%Y-%m-%d')}")

                # Check if article already exists for this week
                existing_article = Article.query.filter(
                    Article.publication_date >= monday,
                    Article.publication_date < next_monday
                ).first()

                if existing_article:
                    logger.warning(f"Article already exists for week of {monday.strftime('%Y-%m-%d')}")
                    return False

                # Check if any articles are currently being generated
                generating_article = Article.query.filter_by(status='generating').first()
                if generating_article:
                    logger.warning("Another article is currently being generated. Please wait.")
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
    parser = argparse.ArgumentParser(description='Generate a single article for a specific date')
    parser.add_argument('--date', type=str, help='Target date in YYYY-MM-DD format')

    args = parser.parse_args()

    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d')
            print(f"\n=== Generating Article for week of {target_date.strftime('%Y-%m-%d')} ===\n")
        except ValueError as e:
            print(f"Error parsing date: {e}")
            sys.exit(1)

    success = generate_article_for_date(target_date)
    exit_code = 0 if success else 1
    print(f"\n=== Article Generation {'Succeeded' if success else 'Failed'} ===\n")
    sys.exit(exit_code)