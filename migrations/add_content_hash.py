import sys
import os
import logging
from datetime import datetime
import hashlib
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import Article

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def generate_content_hash(title: str, content: str) -> str:
    """Generate a hash of the article content."""
    combined_content = f"{title}|{content}"
    return hashlib.sha256(combined_content.encode()).hexdigest()

def add_content_hash():
    """Add content_hash field to articles and populate it."""
    try:
        # Add the column if it doesn't exist
        with app.app_context():
            with db.engine.connect() as conn:
                conn.execute(db.text('ALTER TABLE article ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64)'))
                conn.commit()

            # Update existing articles with content hash
            articles = Article.query.all()
            for article in articles:
                if not article.content_hash:
                    article.content_hash = generate_content_hash(article.title, article.content)

            db.session.commit()
            logger.info("Successfully added and populated content_hash field")
            return True

    except Exception as e:
        logger.error(f"Error adding content hash: {str(e)}")
        with app.app_context():
            db.session.rollback()
        return False

if __name__ == "__main__":
    success = add_content_hash()
    sys.exit(0 if success else 1)