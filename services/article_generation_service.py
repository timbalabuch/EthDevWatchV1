import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union

import pytz
from openai import OpenAI

from app import db
from models import Article, Source
from services.forum_service import ForumService
from services.github_service import GitHubService

logger = logging.getLogger(__name__)

class ArticleGenerationService:
    """New implementation of article generation service with improved status tracking."""
    
    def __init__(self):
        """Initialize the ArticleGenerationService with required clients."""
        try:
            api_key = os.environ.get('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable is not set")
            
            self.openai = OpenAI(api_key=api_key)
            self.model = "gpt-4"
            self.github_service = GitHubService()
            self.forum_service = ForumService()
            self.generation_errors = []
            logger.info("ArticleGenerationService initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ArticleGenerationService: {str(e)}")
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
        """Check for existing articles in the target week."""
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

    def track_error(self, error_msg: str, error_type: str = "generation"):
        """Track errors during generation process."""
        self.generation_errors.append({
            "timestamp": datetime.now(pytz.UTC),
            "type": error_type,
            "message": error_msg
        })
        logger.error(f"Article generation error ({error_type}): {error_msg}")

    def create_placeholder_article(self, target_date: datetime) -> Article:
        """Create a placeholder article in generating status."""
        try:
            article = Article(
                title="Article Generation in Progress...",
                content="The article is currently being generated. Please check back in a few minutes.",
                publication_date=target_date,
                status='generating',
                published_date=datetime.now(pytz.UTC)
            )
            db.session.add(article)
            db.session.commit()
            logger.info(f"Created placeholder article for {target_date.strftime('%Y-%m-%d')}")
            return article
        except Exception as e:
            error_msg = f"Failed to create placeholder article: {str(e)}"
            self.track_error(error_msg, "database")
            raise

    def generate_single_article(self, target_date: Optional[datetime] = None) -> Optional[Article]:
        """Generate a single article with improved status tracking."""
        try:
            # Calculate target date
            target_date = self.get_target_date(target_date)
            logger.info(f"Generating article for week of {target_date.strftime('%Y-%m-%d')}")

            # Check for conflicts
            has_conflict, msg, existing_article = self.check_conflicts(target_date)
            if has_conflict:
                logger.warning(msg)
                return existing_article

            # Create placeholder article
            article = self.create_placeholder_article(target_date)

            try:
                # Fetch GitHub content
                github_content = self.github_service.fetch_recent_content()
                if not github_content:
                    self.track_error("No content fetched from GitHub", "github")
                    return None

                # Generate content using existing service
                # This will be replaced with new implementation in next phase
                from services.content_service import ContentService
                content_service = ContentService()
                
                updated_article = content_service.generate_weekly_summary(
                    github_content,
                    target_date
                )

                if updated_article:
                    logger.info(f"Successfully generated article: {updated_article.title}")
                    return updated_article
                else:
                    self.track_error("Failed to generate article content", "generation")
                    return None

            except Exception as e:
                self.track_error(str(e))
                if article and article.id:
                    db.session.delete(article)
                    db.session.commit()
                raise

        except Exception as e:
            self.track_error(str(e))
            logger.error(f"Fatal error in article generation: {str(e)}")
            return None

    def get_generation_status(self) -> Dict:
        """Get current generation status and errors."""
        try:
            generating_article = Article.query.filter_by(status='generating').first()
            return {
                "is_generating": generating_article is not None,
                "current_article": generating_article.id if generating_article else None,
                "errors": self.generation_errors,
                "last_error": self.generation_errors[-1] if self.generation_errors else None
            }
        except Exception as e:
            logger.error(f"Error getting generation status: {str(e)}")
            return {
                "is_generating": False,
                "current_article": None,
                "errors": [],
                "last_error": None
            }
