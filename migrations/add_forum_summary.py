import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
import logging
from sqlalchemy import text

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def add_forum_summary_column():
    """Add forum_summary column to articles table if it doesn't exist"""
    try:
        with app.app_context():
            # Check if column exists in database
            with db.engine.connect() as conn:
                # Get column info from database
                result = conn.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name='article' AND column_name='forum_summary'")
                )
                has_column = result.fetchone() is not None

            if not has_column:
                logger.info("Adding forum_summary column to articles table")
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE article ADD COLUMN forum_summary TEXT"))
                logger.info("Successfully added forum_summary column")
            else:
                logger.info("forum_summary column already exists in articles table")

    except Exception as e:
        logger.error(f"Error adding forum_summary column: {str(e)}")
        raise

if __name__ == '__main__':
    add_forum_summary_column()
