import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
import logging
from models import Article

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def remove_image_url_column():
    """Remove the image_url column from articles table if it exists"""
    try:
        with app.app_context():
            # Check if column exists in database
            with db.engine.connect() as conn:
                # Get column info from database
                result = conn.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='article' 
                    AND column_name='image_url';
                """)
                has_column = result.fetchone() is not None

            if has_column:
                logger.info("Removing image_url column from articles table")
                with db.engine.connect() as conn:
                    conn.execute("ALTER TABLE article DROP COLUMN IF EXISTS image_url;")
                logger.info("Successfully removed image_url column")
            else:
                logger.info("No image_url column found in articles table")

    except Exception as e:
        logger.error(f"Error removing image_url column: {str(e)}")
        raise

if __name__ == '__main__':
    remove_image_url_column()