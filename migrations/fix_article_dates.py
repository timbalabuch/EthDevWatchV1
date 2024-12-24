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

            # Get all articles ordered by their original dates
            articles = Article.query.order_by(Article.publication_date.asc()).all()

            if not articles:
                print("No articles found")
                return

            # Get the earliest article date
            earliest_article = articles[0]
            earliest_date = earliest_article.publication_date
            if earliest_date.tzinfo is None:
                earliest_date = pytz.UTC.localize(earliest_date)

            # Get Monday of the earliest article's week
            monday = earliest_date - timedelta(days=earliest_date.weekday())
            monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)

            # Group articles by weeks, going forward in time
            current_week = monday
            for article in articles:
                # Set article date to current week's Monday
                if article.publication_date.tzinfo is None:
                    article.publication_date = pytz.UTC.localize(article.publication_date)

                article.publication_date = current_week
                print(f"Setting article '{article.title}' to week of {current_week.strftime('%Y-%m-%d')}")

                # After every second article, move to next week
                if (articles.index(article) + 1) % 2 == 0:
                    current_week = current_week + timedelta(weeks=1)

            db.session.commit()
            print("Successfully updated article dates")

        except Exception as e:
            print(f"Error updating article dates: {e}")
            db.session.rollback()

if __name__ == '__main__':
    fix_article_dates()