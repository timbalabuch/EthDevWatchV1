import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import Article
from datetime import datetime, timedelta
import pytz
import logging

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def fix_article_dates():
    """Fix article dates to properly reflect their weekly periods"""
    with app.app_context():
        try:
            # Get current UTC time
            current_date = datetime.now(pytz.UTC)
            logger.info(f"Current UTC time: {current_date}")

            # Calculate the last completed Sunday (end of last complete week)
            days_since_sunday = current_date.weekday() + 1  # +1 because we want the previous Sunday
            last_completed_sunday = current_date - timedelta(days=days_since_sunday)
            last_completed_sunday = last_completed_sunday.replace(hour=23, minute=59, second=59, microsecond=999999)

            # Calculate the Monday of the last completed week
            last_completed_monday = last_completed_sunday - timedelta(days=6)
            last_completed_monday = last_completed_monday.replace(hour=0, minute=0, second=0, microsecond=0)

            logger.info(f"Last completed week: {last_completed_monday.strftime('%Y-%m-%d')} to {last_completed_sunday.strftime('%Y-%m-%d')}")

            # Delete any articles with future dates
            future_articles = Article.query.filter(Article.publication_date > last_completed_sunday).all()
            for article in future_articles:
                logger.info(f"Removing article dated {article.publication_date}: {article.title}")
                db.session.delete(article)

            # Commit the deletion of future articles first
            db.session.commit()

            # Get remaining articles ordered by their original dates, newest first
            articles = Article.query.order_by(Article.publication_date.desc()).all()

            if not articles:
                logger.info("No articles found")
                return

            # Start with the most recent completed week's Monday and work backwards
            current_monday = last_completed_monday
            processed_weeks = set()

            for article in articles:
                monday_str = current_monday.strftime('%Y-%m-%d')

                # If we already have an article for this week, mark this one as duplicate
                if monday_str in processed_weeks:
                    logger.info(f"Removing duplicate article for week of {monday_str}: {article.title}")
                    db.session.delete(article)
                    continue

                # Update article date to this Monday
                if article.publication_date.tzinfo is None:
                    article.publication_date = pytz.UTC.localize(article.publication_date)

                logger.info(f"Setting article '{article.title}' to week of {monday_str}")
                article.publication_date = current_monday

                # Mark this week as processed and move to previous week
                processed_weeks.add(monday_str)
                current_monday = current_monday - timedelta(weeks=1)

            # Commit all changes
            try:
                db.session.commit()
                logger.info("Successfully updated article dates")
            except Exception as e:
                logger.error(f"Error committing changes: {str(e)}")
                db.session.rollback()
                raise

        except Exception as e:
            logger.error(f"Error updating article dates: {str(e)}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    fix_article_dates()