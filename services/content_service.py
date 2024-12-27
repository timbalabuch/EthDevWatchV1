import json
import logging
import os
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

import pytz
from openai import OpenAI, RateLimitError

from app import app, db  # Add app import
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
            self.model = "gpt-4"  # Using stable model
            self.max_retries = 5
            self.base_delay = 2
            self.max_delay = 60
            self.jitter = 0.1
            self.forum_service = ForumService()
            logger.info("ContentService initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ContentService: {str(e)}")
            raise

    def _format_forum_discussion(self, discussion):
        """Format a single forum discussion with proper date handling."""
        try:
            if not discussion or 'created_at' not in discussion:
                logger.warning("Invalid discussion data format")
                return ''

            # Parse and format the date
            date_str = discussion['created_at']
            try:
                # Make sure to handle both string and datetime inputs
                if isinstance(date_str, str):
                    date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                else:
                    date = date_str
                formatted_date = date.strftime('%B %d, %Y')
            except Exception as e:
                logger.error(f"Error formatting date {date_str}: {str(e)}")
                formatted_date = str(date_str)

            return f"""
                <div class="forum-discussion-item mb-3">
                    <h4 class="mb-2">
                        <a href="{discussion['url']}" target="_blank" class="text-decoration-none">
                            {discussion['title']}
                        </a>
                    </h4>
                    <div class="meta text-muted small mb-2">
                        {formatted_date}
                    </div>
                    <div class="discussion-summary">
                        {discussion.get('summary', '')}
                    </div>
                </div>
            """
        except Exception as e:
            logger.error(f"Error formatting forum discussion: {str(e)}", exc_info=True)
            return ''

    def _format_forum_section(self, discussions, site_name):
        """Format a complete forum section (Magicians or Research)."""
        if not discussions:
            return f'<div class="alert-light p-3 rounded">No discussions found on {site_name} for this period.</div>'

        formatted_discussions = []
        for discussion in discussions:
            formatted = self._format_forum_discussion(discussion)
            if formatted:
                formatted_discussions.append(formatted)

        if not formatted_discussions:
            return f'<div class="alert-light p-3 rounded">Error processing discussions from {site_name}.</div>'

        return ''.join(formatted_discussions)

    def generate_weekly_summary(self, github_content: List[Dict], publication_date: Optional[datetime] = None) -> Optional[Article]:
        """Generate a weekly summary article from GitHub content."""
        if not github_content:
            logger.error("No GitHub content provided for summary generation")
            raise ValueError("GitHub content is required for summary generation")

        try:
            with app.app_context():
                current_date = datetime.now(pytz.UTC)

                # Handle publication date
                if publication_date is None:
                    days_since_monday = current_date.weekday()
                    publication_date = current_date - timedelta(days=days_since_monday)
                    publication_date = publication_date.replace(hour=0, minute=0, second=0, microsecond=0)

                # Ensure date is timezone-aware
                if not isinstance(publication_date, datetime):
                    publication_date = datetime.fromisoformat(str(publication_date))
                if publication_date.tzinfo is None:
                    publication_date = pytz.UTC.localize(publication_date)

                logger.info(f"Starting article generation for date: {publication_date}")

                # Check if article already exists for this week
                existing_article = Article.query.filter(
                    Article.publication_date >= publication_date,
                    Article.publication_date < publication_date + timedelta(days=7)
                ).first()

                if existing_article:
                    logger.info(f"Article already exists for week of {publication_date.strftime('%Y-%m-%d')}")
                    return existing_article

                # Get forum discussions
                try:
                    forum_summary = self.forum_service.get_weekly_forum_summary(publication_date)
                except Exception as e:
                    logger.error(f"Error fetching forum discussions: {str(e)}", exc_info=True)
                    forum_summary = None

                # Generate content using OpenAI
                content = self._generate_content_with_openai(github_content, publication_date)
                if not content:
                    raise ValueError("Failed to generate content with OpenAI")

                # Create article
                article = Article(
                    title="Weekly Ethereum Development Update",
                    content=content,
                    publication_date=publication_date,
                    status='published',
                    published_date=current_date,
                    forum_summary=forum_summary if forum_summary else "No forum discussions available"
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
                logger.info(f"Successfully created article with ID: {article.id}")

                return article

        except Exception as e:
            logger.error(f"Error in generate_weekly_summary: {str(e)}", exc_info=True)
            if 'db' in locals():
                db.session.rollback()
            raise

    def _generate_content_with_openai(self, github_content, publication_date):
        """Generate article content using OpenAI."""
        try:
            logger.info("Starting content generation with OpenAI")

            # Prepare repository summaries
            repo_summaries = []
            for repo, items in self.organize_content_by_repository(github_content).items():
                summary = {
                    'repository': repo,
                    'total_issues': len(items['issues']),
                    'total_commits': len(items['commits']),
                    'sample_issues': [{'title': i['title'], 'url': i['url']} for i in items['issues'][:3]],
                    'sample_commits': [{'title': c['title'], 'url': c['url']} for c in items['commits'][:3]]
                }
                repo_summaries.append(summary)

            # Generate content
            response = self._retry_with_exponential_backoff(
                self.openai.chat.completions.create,
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": """You are a technical writer creating Ethereum development summaries.
                        Write in plain language that anyone can understand. Focus on real-world impact.
                        Structure your response with these sections:
                        1. Overview (What changed and why it matters)
                        2. Repository Updates (What was worked on)
                        3. Technical Highlights (Important changes)
                        4. Next Steps (What's coming up)"""
                    },
                    {
                        "role": "user",
                        "content": f"Create a summary for Ethereum development updates for {publication_date.strftime('%B %d, %Y')}:\n{json.dumps(repo_summaries, indent=2)}"
                    }
                ],
                temperature=0.7,
                max_tokens=2000
            )

            if not response or not response.choices:
                raise ValueError("Invalid response from OpenAI")

            content = response.choices[0].message.content
            logger.info("Successfully generated content with OpenAI")
            return content

        except Exception as e:
            logger.error(f"Error generating content with OpenAI: {str(e)}", exc_info=True)
            raise

    def organize_content_by_repository(self, github_content: List[Dict]) -> Dict:
        """Organize GitHub content by repository."""
        repo_content = {}
        for item in github_content:
            repo = item['repository']
            if repo not in repo_content:
                repo_content[repo] = {'issues': [], 'commits': []}
            if item['type'] == 'issue':
                repo_content[repo]['issues'].append(item)
            elif item['type'] == 'commit':
                repo_content[repo]['commits'].append(item)
        return repo_content

    def _retry_with_exponential_backoff(self, func, *args, **kwargs):
        """Execute a function with exponential backoff retry logic."""
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except RateLimitError as e:
                if attempt == self.max_retries - 1:
                    raise
                delay = min(self.max_delay, (self.base_delay * (2 ** attempt)) + (random.random() * self.jitter))
                logger.warning(f"Rate limit hit, retrying in {delay:.2f} seconds (attempt {attempt + 1}/{self.max_retries})")
                time.sleep(delay)
            except Exception as e:
                logger.error(f"Error in attempt {attempt + 1}: {str(e)}", exc_info=True)
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(self.base_delay * (2 ** attempt))

    def _clean_title(self, title: str) -> str:
        """Clean and format the article title."""
        title = title.replace('Title:', '').strip()
        title = title.replace('"', '').replace("'", '').strip()
        if ':' in title and not any(x in title for x in ['Update', 'Progress', 'Development', 'Enhancement']):
            title = title.split(':', 1)[1].strip()
        return title

    def _extract_content_sections(self, content: str) -> Dict[str, Union[str, List[str]]]:
        """Extract different sections from the content."""
        parts = content.split('\n\n')
        title = self._clean_title(parts[0])

        brief_summary = ''
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
            elif not current_section and len(brief_summary) < 700:
                brief_summary += ' ' + part

        return {
            'title': title,
            'brief_summary': brief_summary.strip(),
            'repo_updates': repo_updates,
            'tech_highlights': tech_highlights,
            'next_steps': next_steps
        }

    def _generate_overview_summary(self, content: Dict) -> str:
        """Generate a concise overview summary of the article content."""
        try:
            messages = [
                {
                    "role": "system",
                    "content": """You are a technical writer creating concise overviews of Ethereum development updates.
                    Create a single paragraph that summarizes the key points, focusing on:
                    1. Community discussions and their impact
                    2. Major repository updates and their significance
                    3. Technical highlights that matter to users

                    Use plain language and focus on real-world impact."""
                },
                {
                    "role": "user",
                    "content": f"""Create a concise overview paragraph that summarizes:

                    Forum Discussions:
                    {content.get('forum_summary', 'No forum discussions available.')}

                    Repository Updates:
                    {' '.join(str(update.get('summary', '')) for update in content.get('repository_updates', []))}

                    Technical Highlights:
                    {' '.join(str(highlight.get('description', '')) for highlight in content.get('technical_highlights', []))}
                    """
                }
            ]

            response = self._retry_with_exponential_backoff(
                self.openai.chat.completions.create,
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )

            if not response or not hasattr(response, 'choices') or not response.choices:
                raise ValueError("Invalid response from OpenAI API")

            overview = response.choices[0].message.content.strip()
            return overview

        except Exception as e:
            logger.error(f"Error generating overview summary: {str(e)}")
            return "Overview generation in progress..."

    def _format_article_content(self, summary_data: Dict) -> str:
        """Format the article content with proper HTML structure."""
        try:
            # Generate overview summary
            overview_summary = self._generate_overview_summary(summary_data)

            article_html = f"""
                <article class="ethereum-article">
                    <div class="overview-section mb-4">
                        <div class="overview-content">
                            {overview_summary}
                        </div>
                    </div>
            """

            # Repository updates section
            if summary_data.get('repository_updates'):
                article_html += f"""
                    <div class="repository-updates mb-4">
                        <h2 class="section-title">Repository Updates</h2>
                        {self._format_repository_updates(summary_data.get('repository_updates', []))}
                    </div>
                """

            # Technical highlights section
            if summary_data.get('technical_highlights'):
                article_html += f"""
                    <div class="technical-highlights mb-4">
                        <h2 class="section-title">Technical Highlights</h2>
                        {self._format_technical_highlights(summary_data.get('technical_highlights', []))}
                    </div>
                """

            # Forum Discussions Section
            forum_data = summary_data.get('forum_discussions', {})
            if isinstance(forum_data, dict) and (forum_data.get('magicians') or forum_data.get('research')):
                article_html += f"""
                    <div class="forum-discussions mb-4">
                        <h2 class="section-title">Forum Discussions</h2>
                        {self._format_forum_section(forum_data.get('magicians', []), 'Magicians')}
                        {self._format_forum_section(forum_data.get('research', []), 'Research')}
                    </div>
                """

            # Next steps section
            if summary_data.get('next_steps'):
                article_html += f"""
                    <div class="next-steps mb-4">
                        <h2 class="section-title">Next Steps</h2>
                        <ul>
                            {''.join(f"<li>{step}</li>" for step in summary_data.get('next_steps', []))}
                        </ul>
                    </div>
                """

            article_html += "</article>"
            logger.info(f"Generated article HTML (length: {len(article_html)})")
            return article_html

        except Exception as e:
            logger.error(f"Error formatting article content: {str(e)}")
            raise

    def _format_repository_updates(self, updates: List[Union[str, Dict]]) -> str:
        """Format repository updates section."""
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

    def _format_technical_highlights(self, highlights: List[Union[str, Dict]]) -> str:
        """Format technical highlights section."""
        formatted_highlights = []
        for highlight in highlights:
            if isinstance(highlight, str):
                highlight_html = f"""
                    <div class="highlight mb-3">
                        <p>{highlight}</p>
                    </div>
                """
            else:
                highlight_html = f"""
                    <div class="highlight mb-3">
                        {f'<h3>{highlight.get("title")}</h3>' if highlight.get("title") else ''}
                        <p>{highlight.get('description', '')}</p>
                        {f'<div class="highlight-impact"><strong>Impact:</strong><p>{highlight.get("impact")}</p></div>' if highlight.get("impact") else ''}
                    </div>
                """
            formatted_highlights.append(highlight_html)
        return '\n'.join(formatted_highlights)

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
        """Organize GitHub content by repository and type."""
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