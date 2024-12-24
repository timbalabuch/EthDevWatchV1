import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import Article
from datetime import datetime, timedelta
import pytz

def fix_article_dates():
    """Fix article dates to properly reflect their weekly periods"""
    with app.app_context():
        try:
            # Get current UTC time
            current_date = datetime.now(pytz.UTC)

            # Get all articles ordered by their original dates, newest first
            articles = Article.query.order_by(Article.publication_date.desc()).all()

            if not articles:
                print("No articles found")
                return

            # Start with the most recent Monday before current date
            last_monday = current_date - timedelta(days=current_date.weekday())
            last_monday = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)

            # Group articles by week, going backwards from most recent
            # Keep only the newest article for each week
            week_counter = 0
            processed_weeks = set()

            for article in articles:
                # Calculate the Monday for this article
                article_monday = last_monday - timedelta(weeks=week_counter)
                article_monday_str = article_monday.strftime('%Y-%m-%d')

                # If we already have an article for this week, delete this one
                if article_monday_str in processed_weeks:
                    print(f"Removing duplicate article for week of {article_monday_str}: {article.title}")
                    db.session.delete(article)
                    continue

                # Update article date to this Monday
                if article.publication_date.tzinfo is None:
                    article.publication_date = pytz.UTC.localize(article.publication_date)

                article.publication_date = article_monday
                print(f"Setting article '{article.title}' to week of {article_monday_str}")

                # Mark this week as processed
                processed_weeks.add(article_monday_str)
                week_counter += 1

            db.session.commit()
            print("Successfully updated article dates")

        except Exception as e:
            print(f"Error updating article dates: {e}")
            db.session.rollback()

if __name__ == '__main__':
    fix_article_dates()