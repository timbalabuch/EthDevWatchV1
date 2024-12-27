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

def create_subscribers_table():
    """Create subscribers table for email notifications"""
    try:
        with app.app_context():
            # Check if table exists
            with db.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'subscriber')")
                )
                table_exists = result.scalar()

            if not table_exists:
                logger.info("Creating subscriber table")
                with db.engine.connect() as conn:
                    # Create the table
                    conn.execute(text("""
                        CREATE TABLE subscriber (
                            id SERIAL PRIMARY KEY,
                            email VARCHAR(255) UNIQUE NOT NULL,
                            confirmed BOOLEAN DEFAULT FALSE,
                            confirmation_token VARCHAR(100),
                            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                    """))
                logger.info("Successfully created subscriber table")
            else:
                logger.info("subscriber table already exists")

    except Exception as e:
        logger.error(f"Error creating subscriber table: {str(e)}")
        raise

if __name__ == '__main__':
    create_subscribers_table()
