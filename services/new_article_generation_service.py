import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union

import pytz
from openai import OpenAI

from app import db
from models import Article, Source
from services.github_service import GitHubService
from services.forum_service import ForumService

logger = logging.getLogger(__name__)

class GenerationError(Exception):
    """Custom exception for article generation errors"""
    def __init__(self, message: str, error_type: str = "generation"):
        self.message = message
        self.error_type = error_type
        super().__init__(self.message)

class NewArticleGenerationService:
    """Service for generating Ethereum development articles with improved error tracking."""

    def __init__(self):
        """Initialize the service with required dependencies."""
        try:
            self.github_service = GitHubService()
            self.forum_service = ForumService()
            self.openai = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
            self.model = "gpt-4"
            self.generation_errors = []
            self.current_article_id = None
            logger.info("NewArticleGenerationService initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize NewArticleGenerationService: {str(e)}")
            raise

    def _track_error(self, message: str, error_type: str = "generation") -> None:
        """Track an error during the generation process."""
        error = {
            "timestamp": datetime.now(pytz.UTC).isoformat(),
            "type": error_type,
            "message": str(message)
        }
        self.generation_errors.append(error)
        logger.error(f"Article generation error ({error_type}): {message}")

    def _get_target_date(self, requested_date: Optional[datetime] = None) -> datetime:
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

    def _check_conflicts(self, target_date: datetime) -> Tuple[bool, str, Optional[Article]]:
        """Check for existing articles and conflicts."""
        try:
            # Check for articles already being generated
            generating_article = Article.query.filter_by(status='generating').first()
            if generating_article:
                return True, "Another article is currently being generated", generating_article

            # Check for existing articles in the target week
            week_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            week_end = week_start + timedelta(days=7)

            existing_article = Article.query.filter(
                Article.publication_date >= week_start,
                Article.publication_date < week_end
            ).first()

            if existing_article:
                return True, f"Article already exists for week of {week_start.strftime('%Y-%m-%d')}", existing_article

            return False, "", None
        except Exception as e:
            self._track_error(f"Error checking for conflicts: {str(e)}", "database")
            raise

    def _create_placeholder(self, target_date: datetime) -> Article:
        """Create a placeholder article in generating status."""
        try:
            article = Article(
                title="Article Generation in Progress",
                content="Please wait while the article is being generated...",
                publication_date=target_date,
                status='generating',
                published_date=datetime.now(pytz.UTC)
            )
            db.session.add(article)
            db.session.commit()
            self.current_article_id = article.id
            logger.info(f"Created placeholder article (ID: {article.id})")
            return article
        except Exception as e:
            self._track_error(f"Failed to create placeholder: {str(e)}", "database")
            raise

    def _fetch_content(self, target_date: datetime) -> Dict:
        """Fetch content from various sources."""
        try:
            # Fetch GitHub content
            github_content = self.github_service.fetch_recent_content(
                start_date=target_date,
                end_date=target_date + timedelta(days=6)
            )
            if not github_content:
                raise GenerationError("No content fetched from GitHub", "github")

            # Fetch forum discussions
            forum_content = self.forum_service.get_weekly_forum_summary(target_date)

            return {
                "github": github_content,
                "forum": forum_content
            }
        except Exception as e:
            self._track_error(f"Error fetching content: {str(e)}", "content_fetch")
            raise

    def _generate_content(self, raw_content: Dict, target_date: datetime) -> Dict:
        """Generate article content using OpenAI."""
        try:
            # Format content for AI processing
            formatted_content = self._format_content_for_ai(raw_content)
            
            # Generate content using OpenAI
            response = self.openai.chat.completions.create(
                model=self.model,
                messages=self._create_prompt(formatted_content, target_date),
                temperature=0.7,
                max_tokens=2000
            )

            if not response.choices:
                raise GenerationError("No content generated by AI", "ai_generation")

            return self._process_ai_response(response.choices[0].message.content)
        except Exception as e:
            self._track_error(f"Error generating content: {str(e)}", "ai_generation")
            raise

    def _format_content_for_ai(self, raw_content: Dict) -> Dict:
        """Format raw content for AI processing."""
        github_content = raw_content.get('github', [])
        forum_content = raw_content.get('forum')

        # Organize GitHub content by repository
        repo_summaries = {}
        for item in github_content:
            repo = item['repository']
            if repo not in repo_summaries:
                repo_summaries[repo] = {
                    'issues': [],
                    'commits': []
                }
            
            if item['type'] == 'issue':
                repo_summaries[repo]['issues'].append(item)
            elif item['type'] == 'commit':
                repo_summaries[repo]['commits'].append(item)

        return {
            'repositories': repo_summaries,
            'forum_discussions': forum_content
        }

    def _create_prompt(self, content: Dict, target_date: datetime) -> List[Dict]:
        """Create the prompt for OpenAI."""
        return [
            {
                "role": "system",
                "content": """You are a technical writer specializing in blockchain technology documentation. 
                Your task is to create comprehensive weekly summaries of Ethereum development that balance technical accuracy with accessibility.
                
                Most important rules:
                1. Use plain language that anyone can understand
                2. Explain complex ideas in simple terms
                3. Focus on real-world impact and benefits
                4. Avoid technical jargon in titles
                5. Make concepts accessible to regular users
                """
            },
            {
                "role": "user",
                "content": f"""Create a simple, easy-to-understand update about Ethereum development for the week of {target_date.strftime('%Y-%m-%d')}.
                Here is the technical content to analyze:
                {json.dumps(content, indent=2)}
                
                Please format the response with these sections:
                1. Title: A clear, non-technical title
                2. Overview: A detailed introduction (700+ characters)
                3. Repository Updates: Key changes and improvements
                4. Technical Highlights: Important technical developments
                5. Next Steps: Upcoming changes and developments
                """
            }
        ]

    def _process_ai_response(self, content: str) -> Dict:
        """Process and structure the AI response."""
        try:
            # Split content into sections
            sections = content.split('\n\n')
            
            # Extract title and remove it from sections
            title = sections[0].replace('Title:', '').strip()
            sections = sections[1:]

            # Initialize section containers
            overview = ""
            repo_updates = []
            tech_highlights = []
            next_steps = []

            current_section = None
            for section in sections:
                section = section.strip()
                if not section:
                    continue

                if 'Repository Updates:' in section:
                    current_section = 'repo'
                    section = section.replace('Repository Updates:', '').strip()
                elif 'Technical Highlights:' in section:
                    current_section = 'tech'
                    section = section.replace('Technical Highlights:', '').strip()
                elif 'Next Steps:' in section:
                    current_section = 'next'
                    section = section.replace('Next Steps:', '').strip()
                
                if current_section == 'repo' and section:
                    repo_updates.append(section)
                elif current_section == 'tech' and section:
                    tech_highlights.append(section)
                elif current_section == 'next' and section:
                    if section.startswith('- '):
                        next_steps.extend([s.strip()[2:] for s in section.split('\n')])
                    else:
                        next_steps.append(section)
                elif not current_section and len(overview) < 700:
                    overview += ' ' + section

            return {
                'title': title,
                'overview': overview.strip(),
                'repository_updates': repo_updates,
                'technical_highlights': tech_highlights,
                'next_steps': next_steps
            }
        except Exception as e:
            self._track_error(f"Error processing AI response: {str(e)}", "content_processing")
            raise

    def _update_article(self, article: Article, content: Dict, raw_content: Dict) -> None:
        """Update the article with generated content."""
        try:
            # Update article content
            article.title = content['title']
            article.content = self._format_article_html(content)
            article.status = 'published'
            
            # Add sources
            for item in raw_content['github']:
                source = Source(
                    url=item['url'],
                    type=item['type'],
                    title=item.get('title', ''),
                    repository=item['repository'],
                    article=article
                )
                db.session.add(source)

            # Update forum summary
            if raw_content.get('forum'):
                article.forum_summary = raw_content['forum']

            db.session.commit()
            logger.info(f"Successfully updated article {article.id}")
        except Exception as e:
            self._track_error(f"Error updating article: {str(e)}", "database")
            raise

    def _format_article_html(self, content: Dict) -> str:
        """Format the article content as HTML."""
        try:
            article_html = f"""
                <article class="ethereum-article">
                    <div class="overview-section mb-4">
                        <div class="overview-content">
                            {content['overview']}
                        </div>
                    </div>
            """

            # Repository updates section
            if content['repository_updates']:
                updates_html = '\n'.join(f'<div class="repository-update mb-3"><p>{update}</p></div>'
                                       for update in content['repository_updates'])
                article_html += f"""
                    <div class="repository-updates mb-4">
                        <h2 class="section-title">Repository Updates</h2>
                        {updates_html}
                    </div>
                """

            # Technical highlights section
            if content['technical_highlights']:
                highlights_html = '\n'.join(f'<div class="highlight mb-3"><p>{highlight}</p></div>'
                                          for highlight in content['technical_highlights'])
                article_html += f"""
                    <div class="technical-highlights mb-4">
                        <h2 class="section-title">Technical Highlights</h2>
                        {highlights_html}
                    </div>
                """

            # Next steps section
            if content['next_steps']:
                steps_html = '\n'.join(f'<li>{step}</li>' for step in content['next_steps'])
                article_html += f"""
                    <div class="next-steps mb-4">
                        <h2 class="section-title">Next Steps</h2>
                        <ul>
                            {steps_html}
                        </ul>
                    </div>
                """

            article_html += "</article>"
            return article_html
        except Exception as e:
            self._track_error(f"Error formatting article HTML: {str(e)}", "formatting")
            raise

    def generate_article(self, target_date: Optional[datetime] = None) -> Optional[Article]:
        """Generate a single article with comprehensive error tracking."""
        try:
            # Reset error tracking for new generation
            self.generation_errors = []
            self.current_article_id = None

            # Calculate target date
            target_date = self._get_target_date(target_date)
            logger.info(f"Starting article generation for week of {target_date.strftime('%Y-%m-%d')}")

            # Check for conflicts
            has_conflict, msg, existing_article = self._check_conflicts(target_date)
            if has_conflict:
                logger.warning(msg)
                return existing_article

            # Create placeholder article
            article = self._create_placeholder(target_date)

            try:
                # Fetch content from sources
                raw_content = self._fetch_content(target_date)

                # Generate article content
                generated_content = self._generate_content(raw_content, target_date)

                # Update article with generated content
                self._update_article(article, generated_content, raw_content)

                logger.info(f"Successfully generated article: {article.title}")
                return article

            except Exception as e:
                # Handle generation failure
                if article and article.id:
                    db.session.delete(article)
                    db.session.commit()
                raise GenerationError(f"Article generation failed: {str(e)}")

        except Exception as e:
            self._track_error(str(e))
            logger.error(f"Fatal error in article generation: {str(e)}")
            return None

    def get_generation_status(self) -> Dict:
        """Get the current generation status and errors."""
        try:
            generating_article = Article.query.filter_by(status='generating').first()
            current_article = None
            if generating_article:
                current_article = {
                    'id': generating_article.id,
                    'title': generating_article.title,
                    'date': generating_article.publication_date.isoformat()
                }

            return {
                "is_generating": generating_article is not None,
                "current_article": current_article,
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
