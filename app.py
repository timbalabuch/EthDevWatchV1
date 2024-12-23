import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager

# Setup logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

try:
    db = SQLAlchemy(model_class=Base)
    app = Flask(__name__)

    # Configuration
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "ethereum-weekly-secret")

    # Database configuration
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not set")

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }

    # Initialize extensions
    db.init_app(app)
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    @login_manager.user_loader
    def load_user(user_id):
        from models import User
        return User.query.get(int(user_id))

    # Create all tables and import routes after db initialization
    with app.app_context():
        logger.info("Creating database tables...")
        db.create_all()
        logger.info("Database tables created successfully")

        # Import routes after db initialization
        from routes import *  # noqa: F403

        # Initialize scheduler
        try:
            from services.scheduler import init_scheduler
            init_scheduler()
            logger.info("Scheduler initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize scheduler: {str(e)}")
            # Continue running even if scheduler fails

    logger.info("Application initialized successfully")

except Exception as e:
    logger.error(f"Failed to initialize application: {str(e)}")
    raise