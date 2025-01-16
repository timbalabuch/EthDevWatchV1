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
                logger.error("OPENAI_API_KEY environment variable is not set")
                raise ValueError("OpenAI API key not configured. Please set up environment variables.")

            self.openai = OpenAI(api_key=api_key)
            self.model = "gpt-4"  # Using stable model
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

        # Ensure date is a Monday and at start of day
        target_date = target_date - timedelta(days=target_date.weekday())
        return target_date.replace(hour=0, minute=0, second=0, microsecond=0)

    def check_conflicts(self, target_date: datetime) -> Tuple[bool, str, Optional[Article]]:
        """Check for existing or in-progress articles."""
        try:
            # First check for any article in generating status
            generating_article = Article.query.filter_by(status='generating').first()
            if generating_article:
                return True, "Another article is currently being generated", generating_article

            # Then check for existing article in the target week
            week_start = target_date
            week_end = week_start + timedelta(days=7)
            existing_article = Article.query.filter(
                Article.publication_date >= week_start,
                Article.publication_date < week_end
            ).first()

            if existing_article:
                msg = f"Article already exists for week of {week_start.strftime('%Y-%m-%d')}"
                return True, msg, existing_article

            return False, "", None

        except Exception as e:
            logger.error(f"Error checking for conflicts: {str(e)}")
            raise

    def get_generation_status(self) -> Dict[str, Union[bool, str, int]]:
        """Get current generation status and any errors."""
        try:
            # Check for generating articles
            generating_article = Article.query.filter_by(status='generating').first()
            if generating_article:
                return {
                    "is_generating": True,
                    "article_id": generating_article.id,
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

            # Check for conflicts and prevent regeneration on deployment
            has_conflict, msg, existing_article = self.check_conflicts(target_date)
            if has_conflict or existing_article:
                logger.warning(f"Article already exists or conflict found: {msg}")
                return existing_article

            try:
                # Fetch GitHub content
                github_content = self.github_service.fetch_recent_content(
                    start_date=target_date,
                    end_date=target_date + timedelta(days=6, hours=23, minutes=59, seconds=59)
                )

                if not github_content:
                    logger.warning("No content found for the specified week")
                    return None

                # Generate the article content
                from services.content_service import ContentService
                content_service = ContentService()

                generated_article = content_service.generate_weekly_summary(
                    github_content,
                    target_date
                )

                if not generated_article:
                    logger.error("Failed to generate article content")
                    return None

                logger.info(f"Successfully generated article: {generated_article.title}")
                return generated_article

            except Exception as e:
                logger.error(f"Error during article generation: {str(e)}")
                return None

        except Exception as e:
            logger.error(f"Fatal error in generate_article: {str(e)}")
            return None

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