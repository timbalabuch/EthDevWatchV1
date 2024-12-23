import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Setup logging
logging.basicConfig(level=logging.DEBUG)
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

    # Import routes after app initialization to avoid circular imports
    from routes import *  # noqa: E402, F403

    with app.app_context():
        logger.info("Creating database tables...")
        db.create_all()
        logger.info("Database tables created successfully")

        from services.scheduler import init_scheduler
        init_scheduler()
        logger.info("Scheduler initialized successfully")

except Exception as e:
    logger.error(f"Failed to initialize application: {str(e)}")
    raise

logger.info("Application initialized successfully")