import json
import logging
import os
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

import pytz
from openai import OpenAI, RateLimitError

from app import db
from models import Article, Source
from services.forum_service import ForumService

logger = logging.getLogger(__name__)

class ContentService:
    """Service for generating and managing article content using OpenAI."""

    def __init__(self):
        """Initialize the ContentService with OpenAI client and forum service."""
        try:
            api_key = os.environ.get('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable is not set")

            self.openai = OpenAI(api_key=api_key)
            self.model = "gpt-4"
            self.max_retries = 5
            self.base_delay = 2  # Increased base delay
            self.max_delay = 60  # Maximum delay in seconds
            self.jitter = 0.1    # Add randomness to delay
            self.forum_service = ForumService()
            logger.info("ContentService initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ContentService: {str(e)}")
            raise

    def _get_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff and jitter."""
        delay = min(
            self.max_delay,
            (self.base_delay * (2 ** attempt)) + (random.random() * self.jitter)
        )
        return delay

    def _retry_with_exponential_backoff(self, func, *args, **kwargs):
        """Execute a function with improved exponential backoff retry logic."""
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except RateLimitError as e:
                last_exception = e
                if attempt == self.max_retries - 1:
                    logger.error(f"Max retries ({self.max_retries}) exceeded: {str(e)}")
                    raise
                delay = self._get_delay(attempt)
                logger.warning(f"Rate limit hit, retrying in {delay:.2f} seconds (attempt {attempt + 1}/{self.max_retries})")
                time.sleep(delay)
            except Exception as e:
                logger.error(f"Unexpected error in attempt {attempt + 1}: {str(e)}")
                last_exception = e
                if attempt == self.max_retries - 1:
                    raise last_exception
                delay = self._get_delay(attempt)
                logger.info(f"Retrying in {delay:.2f} seconds...")
                time.sleep(delay)

    def organize_content_by_repository(self, github_content: List[Dict]) -> Dict[str, Dict]:
        """Organize GitHub content by repository and type.

        Args:
            github_content: List of content items from GitHub

        Returns:
            Dictionary organizing content by repository
        """
        repo_content = {}
        for item in github_content:
            repo = item['repository']
            if repo not in repo_content:
                repo_content[repo] = {
                    'issues': [],
                    'commits': [],
                    'repository': repo
                }

            if item['type'] == 'issue':
                repo_content[repo]['issues'].append(item)
            elif item['type'] == 'commit':
                repo_content[repo]['commits'].append(item)

        return repo_content

    def _clean_title(self, title: str) -> str:
        """Clean and format the article title.

        Args:
            title: Raw title string

        Returns:
            Cleaned and formatted title
        """
        title = title.replace('Title:', '').strip()
        title = title.replace('"', '').replace("'", '').strip()
        if ':' in title and not any(x in title for x in ['Update', 'Progress', 'Development', 'Enhancement']):
            title = title.split(':', 1)[1].strip()
        return title

    def _extract_content_sections(self, content: str) -> Dict[str, Union[str, List[str]]]:
        """Extract different sections from the content.

        Args:
            content: Raw content string

        Returns:
            Dictionary containing extracted sections
        """
        parts = content.split('\n\n')
        title = self._clean_title(parts[0])

        repo_updates = []
        tech_highlights = []
        next_steps = []
        current_section = None

        for part in parts[1:]:
            part = part.strip()
            if not part:
                continue

            if 'Repository Updates:' in part:
                current_section = 'repo'
                part = part.replace('Repository Updates:', '').strip()
            elif 'Technical Highlights:' in part:
                current_section = 'tech'
                part = part.replace('Technical Highlights:', '').strip()
            elif 'Next Steps:' in part:
                current_section = 'next'
                part = part.replace('Next Steps:', '').strip()

            if current_section == 'repo' and part:
                repo_updates.append(part)
            elif current_section == 'tech' and part:
                tech_highlights.append(part)
            elif current_section == 'next' and part:
                if part.startswith('- '):
                    next_steps.extend([step.strip() for step in part.split('\n')])
                else:
                    next_steps.append(part)

        return {
            'title': title,
            'repository_updates': repo_updates,
            'tech_highlights': tech_highlights,
            'next_steps': next_steps
        }

    def _format_repository_updates(self, updates: List[Union[str, Dict]]) -> str:
        """Format repository updates section.

        Args:
            updates: List of repository updates

        Returns:
            Formatted HTML for updates section
        """
        formatted_updates = []
        for update in updates:
            if isinstance(update, str):
                update_html = f"""
                    <div class="repository-update mb-3">
                        <div class="update-summary">
                            <p>{update}</p>
                        </div>
                    </div>
                """
            else:
                update_html = f"""
                    <div class="repository-update mb-3">
                        {f'<h3 class="repository-name">{update.get("repository")}</h3>' if update.get("repository") else ''}
                        <div class="update-summary">
                            <p>{update.get('summary', '')}</p>
                        </div>
                    </div>
                """
            formatted_updates.append(update_html)
        return '\n'.join(formatted_updates)

    def _format_article_content(self, summary_data: Dict) -> str:
        """Format the article content with proper HTML structure."""
        try:
            article_html = f"""
                <article class="ethereum-article">
                    {summary_data.get('repository_updates', '')}
                </article>
            """
            logger.info(f"Generated article HTML (length: {len(article_html)})")
            return article_html

        except Exception as e:
            logger.error(f"Error formatting article content: {str(e)}")
            raise

    def generate_weekly_summary(self, github_content: List[Dict], publication_date: Optional[datetime] = None) -> Optional[Article]:
        """Generate a weekly summary article from GitHub content."""
        if not github_content:
            logger.error("No GitHub content provided for summary generation")
            raise ValueError("GitHub content is required for summary generation")

        try:
            current_date = datetime.now(pytz.UTC)

            # Handle publication date
            if publication_date:
                if not isinstance(publication_date, datetime):
                    publication_date = datetime.fromisoformat(str(publication_date))
                if publication_date.tzinfo is None:
                    publication_date = pytz.UTC.localize(publication_date)
            else:
                days_since_monday = current_date.weekday()
                publication_date = current_date - timedelta(days=days_since_monday)
                publication_date = publication_date.replace(hour=0, minute=0, second=0, microsecond=0)
                publication_date = pytz.UTC.localize(publication_date)

            # Get forum discussions summary with error handling
            forum_summary = None
            forum_error = None
            try:
                forum_summary = self.forum_service.get_weekly_forum_summary(publication_date)
                if not forum_summary:
                    forum_error = "No forum discussions found for this week"
                    logger.warning(forum_error)
            except Exception as e:
                forum_error = f"Error fetching forum discussions: {str(e)}"
                logger.error(forum_error)

            repo_content = self.organize_content_by_repository(github_content)
            if not repo_content:
                logger.warning("No content found to summarize")
                return None

            # Create repository summaries
            repo_summaries = []
            for repo, content in repo_content.items():
                summary = {
                    'repository': repo,
                    'total_issues': len(content['issues']),
                    'total_commits': len(content['commits']),
                    'sample_issues': [{'title': issue['title'], 'url': issue['url']} for issue in content['issues'][:3]],
                    'sample_commits': [{'title': commit['title'], 'url': commit['url']} for commit in content['commits'][:3]]
                }
                repo_summaries.append(summary)

            logger.info(f"Generated summaries for {len(repo_summaries)} repositories")

            # Generate repository content using OpenAI
            messages = [
                {
                    "role": "system",
                    "content": """You are a technical writer specializing in blockchain technology documentation. 
                    Your task is to create a summary ONLY about Ethereum repository updates.

                    STRICT RULES:
                    1. Focus ONLY on code changes, pull requests, and commits
                    2. DO NOT include ANY forum discussions, community feedback, or meeting notes
                    3. Only reference GitHub repository activities
                    4. Each update must link directly to a specific repository change

                    Required sections:
                    1. Repository Updates - Changes from code repositories only
                    2. Technical Highlights - Implementation details and code improvements
                    3. Next Steps - Upcoming repository work and planned code changes"""
                },
                {
                    "role": "user",
                    "content": f"""Create a technical summary focusing ONLY on the GitHub repository updates for the week of {publication_date.strftime('%Y-%m-%d')}.

                    IMPORTANT:
                    - Focus only on code changes, PRs, and commits
                    - No forum discussions or community content
                    - Each point should reference a specific code change
                    - Only discuss repository activities

                    Here are the repository updates to analyze:
                    {json.dumps(repo_summaries, indent=2)}"""
                }
            ]

            logger.info("Sending request to OpenAI API...")
            response = self._retry_with_exponential_backoff(
                self.openai.chat.completions.create,
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=2000
            )

            if not response or not hasattr(response, 'choices') or not response.choices:
                raise ValueError("Invalid response from OpenAI API")

            logger.info("Received response from OpenAI API")
            content = response.choices[0].message.content

            # Extract and process content sections
            sections = self._extract_content_sections(content)

            # Format the repository updates as HTML
            content = self._format_article_content({
                'repository_updates': '\n'.join([
                    '<h2 class="section-title">Repository Updates</h2>',
                    self._format_repository_updates([{'summary': update} for update in sections['repository_updates']]),
                    '<h2 class="section-title mt-5">Technical Highlights</h2>',
                    self._format_repository_updates([{'summary': highlight} for highlight in sections['tech_highlights']]),
                    '<h2 class="section-title mt-5">Next Steps</h2>',
                    '<ul class="next-steps-list">',
                    '\n'.join([f'<li>{step}</li>' for step in sections['next_steps']]),
                    '</ul>'
                ])
            })

            article = Article(
                title=sections['title'],
                content=content,
                publication_date=publication_date,
                status='published',
                published_date=current_date,
                forum_summary=forum_summary if forum_summary else forum_error
            )

            # Add sources
            for item in github_content:
                source = Source(
                    url=item['url'],
                    type=item['type'],
                    title=item.get('title', ''),
                    repository=item['repository'],
                    article=article
                )
                db.session.add(source)

            db.session.add(article)
            db.session.commit()
            logger.info(f"Successfully created article: {article.title}")

            return article

        except Exception as e:
            logger.error(f"Error in generate_weekly_summary: {str(e)}")
            db.session.rollback()
            raise