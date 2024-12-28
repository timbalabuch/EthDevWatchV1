import sys
import os
import logging
from datetime import datetime
import pytz
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import Article

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def cleanup_articles():
    """Clean up articles with future dates in their range and remove duplicates"""
    try:
        with app.app_context():
            current_date = datetime.now(pytz.UTC)
            logger.info(f"Starting cleanup of articles...")

            # Get all articles ordered by publication date
            articles = Article.query.order_by(Article.publication_date.asc()).all()
            week_articles = {}
            articles_to_delete = []

            # First pass: group articles by week and identify future dates
            for article in articles:
                if not article.date_range:
                    logger.warning(f"Article {article.id} has no date range, skipping")
                    continue

                week_start, week_end = article.date_range

                # Add debug logging for date comparisons
                logger.debug(f"Article {article.id}: Start {week_start}, End {week_end}, Current {current_date}")

                # Check for future dates
                if week_end > current_date:
                    logger.info(f"Found article with future dates: {article.title}, end date: {week_end}")
                    articles_to_delete.append(article)
                    continue

                # Group articles by week start date
                week_key = week_start.strftime('%Y-%m-%d')
                if week_key not in week_articles:
                    week_articles[week_key] = []
                week_articles[week_key].append(article)

            # Second pass: handle duplicates
            for week_key, week_group in week_articles.items():
                if len(week_group) > 1:
                    logger.info(f"Found {len(week_group)} articles for week of {week_key}")

                    # Sort by publication date, newest first
                    week_group.sort(key=lambda x: x.publication_date, reverse=True)

                    # Keep only the newest article that starts on Monday
                    kept_article = None
                    for article in week_group:
                        week_start, _ = article.date_range
                        if week_start.weekday() == 0:  # Monday
                            if kept_article is None:
                                kept_article = article
                                logger.info(f"Keeping article {article.id}: {article.title} (published {article.publication_date})")
                            else:
                                logger.info(f"Marking duplicate article {article.id} for deletion: {article.title} (published {article.publication_date})")
                                articles_to_delete.append(article)
                        else:
                            logger.info(f"Marking non-Monday article {article.id} for deletion: {article.title} (starts on {week_start.strftime('%A')})")
                            articles_to_delete.append(article)

                    # If no Monday article was found, keep the newest one
                    if kept_article is None and week_group:
                        kept_article = week_group[0]
                        logger.info(f"No Monday article found, keeping newest article {kept_article.id}: {kept_article.title}")
                        articles_to_delete.extend([a for a in week_group if a != kept_article])

            # Delete problematic articles
            if articles_to_delete:
                logger.info(f"Removing {len(articles_to_delete)} problematic articles")
                for article in articles_to_delete:
                    logger.info(f"Deleting article: {article.title} (week of {article.formatted_date_range})")
                    db.session.delete(article)
                db.session.commit()
                logger.info("Articles removed successfully")
            else:
                logger.info("No problematic articles found")

            return True

    except Exception as e:
        logger.error(f"Error cleaning up articles: {str(e)}")
        db.session.rollback()
        return False

if __name__ == '__main__':
    success = cleanup_articles()
    sys.exit(0 if success else 1)