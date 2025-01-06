import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import Article
from datetime import datetime
import pytz
import logging

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def add_timestamps():
    """Add created_at and updated_at columns to Article table"""
    with app.app_context():
        try:
            # First check if the columns exist
            inspector = db.inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('article')]
            
            if 'created_at' not in columns:
                db.engine.execute('ALTER TABLE article ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP')
                logger.info("Added created_at column")
            
            if 'updated_at' not in columns:
                db.engine.execute('ALTER TABLE article ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP')
                logger.info("Added updated_at column")
            
            # Set timestamps for existing articles
            now = datetime.now(pytz.UTC)
            db.session.execute(
                'UPDATE article SET created_at = :now, updated_at = :now WHERE created_at IS NULL',
                {'now': now}
            )
            
            db.session.commit()
            logger.info("Successfully added timestamp columns")
            
        except Exception as e:
            logger.error(f"Error adding timestamp columns: {str(e)}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    add_timestamps()
