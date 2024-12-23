import sys
import os
import logging
from datetime import datetime, timedelta
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from services.github_service import GitHubService
from services.content_service import ContentService
from models import Article

# Setup logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def cleanup_existing_articles():
    """Remove existing articles before generating new ones"""
    try:
        with app.app_context():
            Article.query.delete()
            db.session.commit()
            logger.info("Cleaned up existing articles")
    except Exception as e:
        logger.error(f"Error cleaning up articles: {str(e)}")
        db.session.rollback()

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

        # Clean up existing articles
        cleanup_existing_articles()

        # Generate articles for past weeks
        success_count = 0
        with app.app_context():
            # Start from 5 weeks ago and work forward
            for week in range(4, -1, -1):  # 4 to 0, representing weeks ago
                # Set publication date to past weeks, starting from oldest
                publication_date = datetime.utcnow() - timedelta(weeks=week)
                # Align to Monday of the week
                monday = publication_date - timedelta(days=publication_date.weekday())
                # Set time to midnight UTC
                publication_date = monday.replace(hour=0, minute=0, second=0, microsecond=0)

                try:
                    logger.info(f"=== Generating article for week {week+1} ===")
                    article = content_service.generate_weekly_summary(github_content)
                    # Update the publication date
                    article.publication_date = publication_date
                    db.session.commit()
                    success_count += 1
                    logger.info(f"Generated article for week {week+1}: {article.title}")
                except Exception as e:
                    logger.error(f"Error generating article for week {week+1}: {str(e)}")
                    db.session.rollback()

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