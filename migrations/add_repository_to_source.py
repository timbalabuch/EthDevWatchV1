import sys
import os
import logging
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from sqlalchemy import text

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def add_repository_column():
    """Add repository column to source table"""
    try:
        with app.app_context():
            # Check if column exists
            with db.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name='source' AND column_name='repository'")
                )
                has_column = result.fetchone() is not None

            if not has_column:
                logger.info("Adding repository column to source table")
                with db.engine.connect() as conn:
                    # Add the column
                    conn.execute(text("ALTER TABLE source ADD COLUMN repository VARCHAR(100)"))
                    # Set default value for existing records
                    conn.execute(text("UPDATE source SET repository = 'ethereum/pm' WHERE repository IS NULL"))
                    # Make it not nullable
                    conn.execute(text("ALTER TABLE source ALTER COLUMN repository SET NOT NULL"))
                logger.info("Successfully added repository column")
            else:
                logger.info("Repository column already exists in source table")

    except Exception as e:
        logger.error(f"Error adding repository column: {str(e)}")
        raise

if __name__ == '__main__':
    add_repository_column()
