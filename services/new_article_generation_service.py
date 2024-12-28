import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Union

import pytz
from openai import OpenAI

from app import db
from models import Article, Source
from services.github_service import GitHubService
from services.forum_service import ForumService

# Configure logging
logger = logging.getLogger(__name__)

class NewArticleGenerationService:
    """New implementation of article generation service with improved status tracking."""

    def __init__(self):
        """Initialize the service with required clients."""
        try:
            api_key = os.environ.get('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable is not set")

            self.openai = OpenAI(api_key=api_key)
            self.model = "gpt-4"  # Using latest stable model
            self.github_service = GitHubService()
            self.forum_service = ForumService()
            logger.info("NewArticleGenerationService initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize NewArticleGenerationService: {str(e)}")
            raise

    def get_target_date(self, requested_date: Optional[datetime] = None) -> datetime:
        """Calculate the appropriate target date for article generation."""
        current_date = datetime.now(pytz.UTC)

        if requested_date:
            if not requested_date.tzinfo:
                requested_date = pytz.UTC.localize(requested_date)
            target_date = requested_date
        else:
            # Get the most recent past Monday
            days_since_monday = current_date.weekday()
            target_date = current_date - timedelta(days=days_since_monday + 7)

        # Ensure date is a Monday
        target_date = target_date - timedelta(days=target_date.weekday())
        return target_date.replace(hour=0, minute=0, second=0, microsecond=0)

    def check_conflicts(self, target_date: datetime) -> Tuple[bool, str, Optional[Article]]:
        """Check for existing or in-progress articles."""
        # First check for any article in generating status
        generating_article = Article.query.filter_by(status='generating').first()
        if generating_article:
            # If an article has been in generating status for more than 10 minutes, mark it as failed
            generation_timeout = datetime.now(pytz.UTC) - timedelta(minutes=10)
            if generating_article.published_date and generating_article.published_date < generation_timeout:
                generating_article.status = 'failed'
                generating_article.content = "<div class='alert alert-danger'>Article generation timed out</div>"
                db.session.commit()
                logger.warning(f"Article {generating_article.id} marked as failed due to timeout")
            else:
                return True, "Another article is currently being generated", generating_article

        # Then check for existing article in the target week
        week_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)
        existing_article = Article.query.filter(
            Article.publication_date >= week_start,
            Article.publication_date < week_end
        ).first()

        if existing_article:
            msg = f"Article already exists for week of {week_start.strftime('%Y-%m-%d')}"
            return True, msg, existing_article

        return False, "", None

    def create_placeholder_article(self, target_date: datetime) -> Article:
        """Create a placeholder article with 'generating' status."""
        try:
            article = Article(
                title="Generating Article...",
                content="<div class='alert alert-info'>Article content is being generated...</div>",
                publication_date=target_date,
                status='generating',
                published_date=datetime.now(pytz.UTC)  # Add published_date for timeout tracking
            )
            db.session.add(article)
            db.session.commit()
            logger.info(f"Created placeholder article with ID: {article.id}")
            return article
        except Exception as e:
            logger.error(f"Error creating placeholder article: {str(e)}")
            db.session.rollback()
            raise

    def update_article_status(self, article: Article, status: str, error: Optional[str] = None) -> None:
        """Update article status and error message if any."""
        try:
            article.status = status
            if error:
                article.content = f"<div class='alert alert-danger'>{error}</div>"
            if status == 'published':
                article.published_date = datetime.now(pytz.UTC)
            db.session.commit()
            logger.info(f"Updated article {article.id} status to: {status}")
        except Exception as e:
            logger.error(f"Error updating article status: {str(e)}")
            db.session.rollback()
            raise

    def get_generation_status(self) -> Dict[str, Union[bool, str, int]]:
        """Get current generation status and any errors."""
        try:
            # First cleanup any stale generating articles
            generating_articles = Article.query.filter_by(status='generating').all()
            for article in generating_articles:
                if article.published_date:
                    generation_timeout = datetime.now(pytz.UTC) - timedelta(minutes=10)
                    if article.published_date < generation_timeout:
                        article.status = 'failed'
                        article.content = "<div class='alert alert-danger'>Article generation timed out</div>"
                        db.session.commit()
                        logger.warning(f"Article {article.id} marked as failed due to timeout")

            # Get current status after cleanup
            generating_article = Article.query.filter_by(status='generating').first()
            if generating_article:
                return {
                    "is_generating": True,
                    "article_id": generating_article.id,
                    "start_time": generating_article.published_date.isoformat() if generating_article.published_date else None,
                    "status": "generating",
                    "error": None
                }

            # Check for recent failed articles
            failed_article = Article.query.filter_by(status='failed').order_by(Article.publication_date.desc()).first()
            if failed_article:
                return {
                    "is_generating": False,
                    "article_id": failed_article.id,
                    "status": "failed",
                    "error": failed_article.content  # Error message is stored in content for failed articles
                }

            return {
                "is_generating": False,
                "article_id": None,
                "status": "idle",
                "error": None
            }

        except Exception as e:
            logger.error(f"Error getting generation status: {str(e)}")
            return {
                "is_generating": False,
                "status": "error",
                "error": str(e)
            }

    def generate_article(self, target_date: Optional[datetime] = None) -> Optional[Article]:
        """Generate a new article with improved status tracking."""
        try:
            # Calculate target date
            target_date = self.get_target_date(target_date)
            logger.info(f"Starting article generation for week of {target_date.strftime('%Y-%m-%d')}")

            # Check for conflicts
            has_conflict, msg, existing_article = self.check_conflicts(target_date)
            if has_conflict:
                logger.warning(msg)
                return existing_article

            # Create placeholder article
            article = self.create_placeholder_article(target_date)

            try:
                # Fetch GitHub content
                github_content = self.github_service.fetch_recent_content(
                    start_date=target_date,
                    end_date=target_date + timedelta(days=6, hours=23, minutes=59, seconds=59)
                )

                if not github_content:
                    error_msg = "No content found for the specified week"
                    self.update_article_status(article, 'failed', error_msg)
                    return None

                # Use existing content service for now
                # This will be replaced with new implementation in next phase
                from services.content_service import ContentService
                content_service = ContentService()

                generated_article = content_service.generate_weekly_summary(
                    github_content,
                    target_date
                )

                if not generated_article:
                    error_msg = "Failed to generate article content"
                    self.update_article_status(article, 'failed', error_msg)
                    return None

                # Update placeholder with generated content
                article.title = generated_article.title
                article.content = generated_article.content
                article.forum_summary = generated_article.forum_summary
                article.status = 'published'
                article.published_date = datetime.now(pytz.UTC)

                # Add sources
                for source in generated_article.sources:
                    source.article = article
                    db.session.add(source)

                db.session.commit()
                logger.info(f"Successfully generated article: {article.title}")
                return article

            except Exception as e:
                error_msg = f"Error during article generation: {str(e)}"
                self.update_article_status(article, 'failed', error_msg)
                logger.error(error_msg)
                return None

        except Exception as e:
            logger.error(f"Fatal error in generate_article: {str(e)}")
            return None