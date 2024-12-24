import sys
import os
import logging
from datetime import datetime, timedelta
import pytz

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import Article, Source
from services.github_service import GitHubService
from services.content_service import ContentService

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_week_dates(publication_date):
    """Get the start and end dates for the week of the given publication date"""
    # Ensure date is timezone-aware
    if publication_date.tzinfo is None:
        publication_date = pytz.UTC.localize(publication_date)
    
    # Get Monday of the week
    monday = publication_date - timedelta(days=publication_date.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Get Sunday of the week
    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    
    return monday, sunday

def regenerate_article(article, github_service, content_service):
    """Regenerate a single article with content from all repositories"""
    try:
        # Get the week's date range for the article
        start_date = article.publication_date
        if start_date.tzinfo is None:
            start_date = pytz.UTC.localize(start_date)

        # Ensure we're using the Monday of the week
        start_date = start_date - timedelta(days=start_date.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=6, hours=23, minutes=59, seconds=59)

        logger.info(f"Regenerating article for week of {start_date.strftime('%Y-%m-%d')}")

        # Check if this is already the primary article for this week
        primary_article = Article.query.filter(
            Article.publication_date >= start_date,
            Article.publication_date <= end_date,
            Article.id != article.id  # Exclude current article
        ).order_by(Article.id.asc()).first()

        if primary_article and primary_article.id < article.id:
            logger.info(f"Skipping duplicate article {article.id} as primary article {primary_article.id} exists")
            # Delete this duplicate article and move its sources to the primary article
            Source.query.filter_by(article_id=article.id).update({"article_id": primary_article.id})
            db.session.delete(article)
            db.session.commit()
            return True

        # Fetch content from all repositories
        github_content = github_service.fetch_recent_content(
            start_date=start_date,
            end_date=end_date
        )

        if not github_content:
            logger.warning(f"No content found for week of {start_date.strftime('%Y-%m-%d')}")
            return False

        logger.info(f"Found {len(github_content)} items from all repositories")

        # Generate new article content
        new_article = content_service.generate_weekly_summary(
            github_content,
            publication_date=start_date  # Use the original article's date
        )

        if not new_article:
            logger.error("Failed to generate new article content")
            return False

        # Update existing article
        article.title = new_article.title
        article.content = new_article.content
        article.publication_date = start_date

        # Delete old sources
        Source.query.filter_by(article_id=article.id).delete()

        # Add new sources
        for item in github_content:
            source = Source(
                url=item['url'],
                type=item['type'],
                title=item.get('title', ''),
                repository=item['repository'],
                article=article
            )
            db.session.add(source)

        db.session.commit()
        logger.info(f"Successfully regenerated article: {article.title}")
        return True

    except Exception as e:
        logger.error(f"Error regenerating article: {str(e)}")
        db.session.rollback()
        return False

def regenerate_all_articles():
    """Regenerate all existing articles with content from all repositories"""
    try:
        with app.app_context():
            # Initialize services
            github_service = GitHubService()
            content_service = ContentService()
            
            # Get all articles ordered by date
            articles = Article.query.order_by(Article.publication_date.desc()).all()
            
            if not articles:
                logger.info("No articles found to regenerate")
                return True
            
            logger.info(f"Found {len(articles)} articles to regenerate")
            
            success_count = 0
            for article in articles:
                try:
                    logger.info(f"Processing article from {article.publication_date.strftime('%Y-%m-%d')}")
                    
                    if regenerate_article(article, github_service, content_service):
                        success_count += 1
                        logger.info(f"Successfully regenerated article {success_count}/{len(articles)}")
                    else:
                        logger.warning(f"Failed to regenerate article from {article.publication_date.strftime('%Y-%m-%d')}")
                    
                    # Add delay between articles to handle rate limits
                    if success_count > 0 and success_count < len(articles):
                        delay = 30  # 30 seconds between generations
                        logger.info(f"Waiting {delay} seconds before next article...")
                        import time
                        time.sleep(delay)
                        
                except Exception as e:
                    logger.error(f"Error processing article: {str(e)}")
                    continue
            
            logger.info(f"Regeneration complete. Successfully regenerated {success_count}/{len(articles)} articles")
            return success_count > 0
            
    except Exception as e:
        logger.error(f"Fatal error in article regeneration: {str(e)}")
        return False

if __name__ == "__main__":
    print("\n=== Starting Article Regeneration ===\n")
    success = regenerate_all_articles()
    exit_code = 0 if success else 1
    print(f"\n=== Article Regeneration {'Succeeded' if success else 'Failed'} ===\n")
    sys.exit(exit_code)