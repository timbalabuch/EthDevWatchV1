import sys
import os
import logging
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import Article

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def cleanup_future_articles():
    """Remove any articles with future publication dates"""
    try:
        with app.app_context():
            current_date = datetime.utcnow()
            
            # Find articles with future dates
            future_articles = Article.query.filter(
                Article.publication_date > current_date
            ).all()
            
            if not future_articles:
                logger.info("No future articles found")
                return True
                
            # Log the articles that will be removed
            logger.info(f"Found {len(future_articles)} articles with future dates")
            for article in future_articles:
                logger.info(f"Removing article: {article.title} (Date: {article.publication_date})")
                db.session.delete(article)
            
            db.session.commit()
            logger.info("Successfully removed all future articles")
            return True
            
    except Exception as e:
        logger.error(f"Error cleaning up future articles: {str(e)}")
        return False

if __name__ == "__main__":
    success = cleanup_future_articles()
    exit_code = 0 if success else 1
    sys.exit(exit_code)
