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

            # Calculate the last completed Sunday (end of last complete week)
            days_since_sunday = current_date.weekday() + 1  # +1 because we want the previous Sunday
            last_completed_sunday = current_date - timedelta(days=days_since_sunday)
            last_completed_sunday = last_completed_sunday.replace(hour=23, minute=59, second=59, microsecond=999999)

            # Calculate the Monday of the last completed week
            last_completed_monday = last_completed_sunday - timedelta(days=6)
            last_completed_monday = last_completed_monday.replace(hour=0, minute=0, second=0, microsecond=0)

            print(f"Last completed week: {last_completed_monday.strftime('%Y-%m-%d')} to {last_completed_sunday.strftime('%Y-%m-%d')}")

            # Get all articles ordered by their original dates, newest first
            articles = Article.query.order_by(Article.publication_date.desc()).all()

            if not articles:
                print("No articles found")
                return

            # Delete any articles with future dates
            future_articles = Article.query.filter(Article.publication_date > last_completed_sunday).all()
            for article in future_articles:
                print(f"Removing future article dated {article.publication_date}: {article.title}")
                db.session.delete(article)

            # Start with the most recent completed week's Monday and work backwards
            current_monday = last_completed_monday
            processed_weeks = set()

            for article in articles:
                # Skip articles that were marked for deletion
                if article in future_articles:
                    continue

                monday_str = current_monday.strftime('%Y-%m-%d')

                # If we already have an article for this week, delete this one
                if monday_str in processed_weeks:
                    print(f"Removing duplicate article for week of {monday_str}: {article.title}")
                    db.session.delete(article)
                    continue

                # Update article date to this Monday
                if article.publication_date.tzinfo is None:
                    article.publication_date = pytz.UTC.localize(article.publication_date)

                article.publication_date = current_monday
                print(f"Setting article '{article.title}' to week of {monday_str}")

                # Mark this week as processed and move to previous week
                processed_weeks.add(monday_str)
                current_monday = current_monday - timedelta(weeks=1)

            db.session.commit()
            print("Successfully updated article dates")

        except Exception as e:
            print(f"Error updating article dates: {e}")
            db.session.rollback()

if __name__ == '__main__':
    fix_article_dates()