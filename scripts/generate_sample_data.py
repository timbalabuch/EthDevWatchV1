import sys
import os
import logging
from datetime import datetime, timedelta
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from services.github_service import GitHubService
from services.content_service import ContentService

# Setup logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

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

        # Generate 5 articles for past weeks
        success_count = 0
        with app.app_context():
            for week in range(5):
                # Set publication date to past weeks
                publication_date = datetime.utcnow() - timedelta(weeks=week+1)

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