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

# Strict environment validation
is_production = os.environ.get('REPL_ENVIRONMENT') == 'production'
is_deployment = os.environ.get('REPLIT_DEPLOYMENT') == '1'
logger.info(f"Running in {'production' if is_production else 'development'} environment")
logger.info(f"Deployment status: {'deployment' if is_deployment else 'local'}")

if is_production and not is_deployment:
    logger.error("Production environment detected without deployment flag - preventing startup")
    raise EnvironmentError("Cannot run production environment locally")

# Configure database URL based on environment
if is_production:
    # Use PostgreSQL in production
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set in production environment")
        raise ValueError("DATABASE_URL must be set in production environment")
    logger.info("Using production PostgreSQL database")
else:
    # Use SQLite for local development
    database_url = "sqlite:///development.db"
    logger.info("Using local SQLite database for development")

# Strict environment validation
is_production = os.environ.get('REPL_ENVIRONMENT') == 'production'
is_deployment = os.environ.get('REPLIT_DEPLOYMENT') == '1'
logger.info(f"Running in {'production' if is_production else 'development'} environment")
logger.info(f"Deployment status: {'deployment' if is_deployment else 'local'}")

if is_production and not is_deployment:
    logger.error("Production environment detected without deployment flag - preventing startup")
    raise EnvironmentError("Cannot run production environment locally")

# Configure database URL based on environment
if is_production:
    # Use PostgreSQL in production
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set in production environment")
        raise ValueError("DATABASE_URL must be set in production environment")
    logger.info("Using production PostgreSQL database")
else:
    # Use SQLite for local development
    database_url = "sqlite:///development.db"
    logger.info("Using local SQLite database for development")

# Configure SQLAlchemy
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_size": 5,
    "max_overflow": 10,
    "pool_timeout": 30
} if is_production else {}  # Only use connection pool in production
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize extensions
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
    """Remove any articles with future dates in development environment"""
    try:
        # Strict production check
        is_production = os.environ.get('REPL_ENVIRONMENT') == 'production'
        if is_production:
            logger.warning("Cleanup operation attempted in production - skipping")
            return

        from models import Article
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

# Initialize database and load routes
with app.app_context():
    try:
        logger.info("Creating database tables...")
        # Import models here to ensure they're registered with SQLAlchemy
        from models import Article, Source, BlockchainTerm, User

        # Check if tables exist before creating
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()

        if not existing_tables:
            logger.info("No existing tables found, creating database schema")
            db.create_all()
            logger.info("Database tables created successfully")
        else:
            logger.info(f"Found existing tables: {', '.join(existing_tables)}")

        if not is_production:  # Only run cleanup in development
            cleanup_future_articles()

        # Import routes after database initialization
        from routes import *
        logger.info("Routes imported successfully")

        try:
            from services.scheduler import init_scheduler
            init_scheduler()
            logger.info("Scheduler initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize scheduler: {str(e)}")

    except Exception as e:
        logger.error(f"Failed to initialize application: {str(e)}")
        raise