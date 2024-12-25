import logging
from flask_migrate import Migrate
from app import app, db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def upgrade():
    """Add forum discussions columns to article table."""
    try:
        with app.app_context():
            # Add columns if they don't exist
            db.session.execute("""
                DO $$ 
                BEGIN 
                    BEGIN
                        ALTER TABLE article ADD COLUMN magicians_discussions TEXT;
                    EXCEPTION
                        WHEN duplicate_column THEN 
                        RAISE NOTICE 'magicians_discussions column already exists';
                    END;
                    
                    BEGIN
                        ALTER TABLE article ADD COLUMN ethresearch_discussions TEXT;
                    EXCEPTION
                        WHEN duplicate_column THEN 
                        RAISE NOTICE 'ethresearch_discussions column already exists';
                    END;
                END $$;
            """)
            db.session.commit()
            logger.info("Successfully added forum discussions columns")
    except Exception as e:
        logger.error(f"Error adding forum discussions columns: {str(e)}")
        raise

def downgrade():
    """Remove forum discussions columns from article table."""
    try:
        with app.app_context():
            db.session.execute("""
                ALTER TABLE article 
                DROP COLUMN IF EXISTS magicians_discussions,
                DROP COLUMN IF EXISTS ethresearch_discussions;
            """)
            db.session.commit()
            logger.info("Successfully removed forum discussions columns")
    except Exception as e:
        logger.error(f"Error removing forum discussions columns: {str(e)}")
        raise

if __name__ == '__main__':
    logger.info("Running forum discussions migration")
    upgrade()
