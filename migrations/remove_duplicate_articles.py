import sys
import os
import logging
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import Article, Source
from sqlalchemy import text, func

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def remove_duplicate_articles():
    """Remove duplicate articles while preserving sources"""
    try:
        with app.app_context():
            # Find groups of duplicate articles by date
            duplicate_groups = db.session.query(
                func.date_trunc('day', Article.publication_date).label('pub_date'),
                func.array_agg(Article.id).label('article_ids'),
                func.count(Article.id).label('count')
            ).group_by(
                func.date_trunc('day', Article.publication_date)
            ).having(
                func.count(Article.id) > 1
            ).all()

            if not duplicate_groups:
                logger.info("No duplicate articles found")
                return

            for group in duplicate_groups:
                pub_date = group.pub_date
                article_ids = group.article_ids
                
                logger.info(f"Processing duplicate group for date {pub_date}")
                logger.info(f"Found {len(article_ids)} articles")

                # Keep the article with the lowest ID (earliest)
                keep_id = min(article_ids)
                remove_ids = [id for id in article_ids if id != keep_id]

                logger.info(f"Keeping article {keep_id}, removing articles {remove_ids}")

                try:
                    # Update sources to point to the kept article
                    Source.query.filter(
                        Source.article_id.in_(remove_ids)
                    ).update(
                        {"article_id": keep_id},
                        synchronize_session=False
                    )

                    # Delete duplicate articles
                    Article.query.filter(
                        Article.id.in_(remove_ids)
                    ).delete(
                        synchronize_session=False
                    )

                    # Commit changes for this group
                    db.session.commit()
                    logger.info(f"Successfully processed duplicate group for {pub_date}")

                except Exception as e:
                    logger.error(f"Error processing duplicate group: {str(e)}")
                    db.session.rollback()
                    continue

            logger.info("Duplicate removal completed successfully")

    except Exception as e:
        logger.error(f"Error removing duplicate articles: {str(e)}")
        db.session.rollback()
        raise

if __name__ == '__main__':
    remove_duplicate_articles()
