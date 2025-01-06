
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
import logging
from sqlalchemy import text

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def add_custom_url_column():
    try:
        with app.app_context():
            with db.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name='article' AND column_name='custom_url'")
                )
                has_column = result.fetchone() is not None

            if not has_column:
                logger.info("Adding custom_url column to article table")
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE article ADD COLUMN custom_url VARCHAR(200) UNIQUE"))
                logger.info("Successfully added custom_url column")
            else:
                logger.info("custom_url column already exists")

    except Exception as e:
        logger.error(f"Error adding custom_url column: {str(e)}")
        raise

if __name__ == '__main__':
    add_custom_url_column()
