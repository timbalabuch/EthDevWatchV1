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

def add_repo_update_sections():
    """Add new columns for repo update sections to articles table"""
    try:
        with app.app_context():
            logger.info("Adding new columns for repo update sections")
            with db.engine.connect() as conn:
                # Add technical_highlights column
                conn.execute(text("ALTER TABLE article ADD COLUMN IF NOT EXISTS technical_highlights TEXT"))
                # Add meeting_summaries column
                conn.execute(text("ALTER TABLE article ADD COLUMN IF NOT EXISTS meeting_summaries TEXT"))
                # Add next_steps column
                conn.execute(text("ALTER TABLE article ADD COLUMN IF NOT EXISTS next_steps TEXT"))
                
                # Commit the changes
                conn.commit()
            
            logger.info("Successfully added repo update section columns")

    except Exception as e:
        logger.error(f"Error adding repo update section columns: {str(e)}")
        raise

if __name__ == '__main__':
    add_repo_update_sections()
