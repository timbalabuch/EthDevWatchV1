
import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager
import pytz
from datetime import datetime

# Setup logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

# Initialize extensions first without the app
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

# Create the app
app = Flask(__name__)

# Setup config
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "ethereum-weekly-secret")
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise ValueError("DATABASE_URL environment variable is not set")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize extensions with app
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
    """Remove any articles with future dates"""
    from models import Article
    try:
        current_time = datetime.now(pytz.UTC)
        future_articles = Article.query.filter(Article.publication_date > current_time).all()

        if future_articles:
            logger.info(f"Found {len(future_articles)} articles with future dates")
            for article in future_articles:
                logger.info(f"Removing future dated article: {article.title}")
                db.session.delete(article)
            db.session.commit()
            logger.info("Successfully removed all future dated articles")
        else:
            logger.info("No future articles found")
    except Exception as e:
        logger.error(f"Error cleaning up future articles: {str(e)}")
        db.session.rollback()

# Initialize database and application
with app.app_context():
    try:
        # Create database tables
        logger.info("Creating database tables...")
        db.create_all()
        logger.info("Database tables created successfully")

        # Clean up any future dated articles
        cleanup_future_articles()

        # Import routes after db initialization to avoid circular imports
        from routes import *

        # Initialize scheduler after routes are loaded
        try:
            from services.scheduler import init_scheduler
            init_scheduler()
            logger.info("Scheduler initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize scheduler: {str(e)}")

        logger.info("Application initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize application: {str(e)}")
        raise
