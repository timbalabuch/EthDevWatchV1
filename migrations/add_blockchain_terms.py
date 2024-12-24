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

def create_blockchain_terms_table():
    """Create blockchain_term table"""
    try:
        with app.app_context():
            # Check if table exists
            with db.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'blockchain_term')")
                )
                table_exists = result.scalar()

            if not table_exists:
                logger.info("Creating blockchain_term table")
                with db.engine.connect() as conn:
                    # Create the table
                    conn.execute(text("""
                        CREATE TABLE blockchain_term (
                            id SERIAL PRIMARY KEY,
                            term VARCHAR(100) UNIQUE NOT NULL,
                            explanation TEXT NOT NULL,
                            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                    """))
                logger.info("Successfully created blockchain_term table")
            else:
                logger.info("blockchain_term table already exists")

    except Exception as e:
        logger.error(f"Error creating blockchain_term table: {str(e)}")
        raise

if __name__ == '__main__':
    create_blockchain_terms_table()
