import os
import logging
from datetime import datetime
import pytz
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

app = Flask(__name__)

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "ethereum-weekly-secret")
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise ValueError("DATABASE_URL environment variable is not set")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
    "pool_timeout": 30,
    "max_overflow": 5
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    from models import User
    try:
        return User.query.get(int(user_id))
    except Exception as e:
        logger.error(f"Error loading user: {str(e)}")
        return None

def cleanup_future_articles():
    from models import Article, Source
    try:
        current_time = datetime.now(pytz.UTC)
        # Find and remove duplicate articles (keep the newest one for each week)
        articles = Article.query.order_by(Article.publication_date.asc()).all()
        weeks = {}  # Dictionary to track articles by week
        articles_to_delete = []

        for article in articles:
            week_start = article.publication_date.replace(hour=0, minute=0, second=0, microsecond=0)
            week_key = week_start.strftime('%Y-%m-%d')

            if week_key in weeks:
                # If we already have an article for this week, mark the older one for deletion
                existing_article = weeks[week_key]
                if article.publication_date > existing_article.publication_date:
                    articles_to_delete.append(existing_article)
                    weeks[week_key] = article
                else:
                    articles_to_delete.append(article)
            else:
                weeks[week_key] = article

        if articles_to_delete:
            for article in articles_to_delete:
                # First delete associated sources
                Source.query.filter_by(article_id=article.id).delete()
                db.session.delete(article)
            db.session.commit()
            logger.info(f"Successfully removed {len(articles_to_delete)} duplicate articles")

        future_articles = Article.query.filter(Article.publication_date > current_time).all()
        if future_articles:
            for article in future_articles:
                Source.query.filter_by(article_id=article.id).delete()
                db.session.delete(article)
            db.session.commit()
            logger.info("Successfully removed future articles")
    except Exception as e:
        logger.error(f"Error cleaning up articles: {str(e)}")
        db.session.rollback()

with app.app_context():
    try:
        db.create_all()
        cleanup_future_articles()
        from routes import *
        try:
            from services.scheduler import init_scheduler
            # Initialize scheduler but don't auto-start unless explicitly enabled
            init_scheduler(auto_start=False)
            logger.info("Application initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize scheduler: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to initialize application: {str(e)}")
        raise