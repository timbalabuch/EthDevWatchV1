
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
    logger.warning("DATABASE_URL not set, using SQLite fallback")
    database_url = "sqlite:///fallback.db"

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 280,
    "pool_pre_ping": True,
    "pool_size": 10,
    "max_overflow": 20,
    "pool_timeout": 30
}
app.config["SQLALCHEMY_POOL_RECYCLE"] = 280
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
    from models import Article
    try:
        current_time = datetime.now(pytz.UTC)
        future_articles = Article.query.filter(Article.publication_date > current_time).all()
        if future_articles:
            for article in future_articles:
                db.session.delete(article)
            db.session.commit()
            logger.info("Successfully removed future articles")
    except Exception as e:
        logger.error(f"Error cleaning up future articles: {str(e)}")
        db.session.rollback()

with app.app_context():
    try:
        db.create_all()
        cleanup_future_articles()
        from routes import *
        try:
            from services.scheduler import init_scheduler
            init_scheduler()
            logger.info("Application initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize scheduler: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to initialize application: {str(e)}")
        raise
