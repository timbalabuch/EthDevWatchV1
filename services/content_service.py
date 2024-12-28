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
                    Create two paragraph that summarizes the key points, focusing on:
                    1. Major technical changes and their significance
                    2. Repository updates that affect users
                    3. Development progress and milestones

                    Use plain language and focus on real-world impact.
                    Avoid technical jargon unless absolutely necessary."""
                },
                {
                    "role": "user",
                    "content": f"""Create a concise overview paragraph that summarizes these updates:

                    Repository Updates:
                    {' '.join(str(update.get('summary', '')) for update in content.get('repository_updates', []))}

                    Technical Highlights:
                    {' '.join(str(highlight.get('description', '')) for highlight in content.get('technical_highlights', []))}
                    """
                }
            ]

            logger.info("Sending request to OpenAI API for overview generation...")
            response = self._retry_with_exponential_backoff(
                self.openai.chat.completions.create,
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )

            if not response or not hasattr(response, 'choices') or not response.choices:
                logger.error("Invalid response from OpenAI API")
                return "Overview generation in progress..."

            overview = response.choices[0].message.content.strip()
            logger.info(f"Successfully generated overview of length: {len(overview)}")
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

    def _format_technical_highlights(self, highlights: List[Union[str, Dict]]) -> str:
        """Format technical highlights section.

        Args:
            highlights: List of technical highlights

        Returns:
            Formatted HTML for highlights section
        """
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

    def check_date_range_conflicts(self, target_date: datetime) -> tuple[bool, Optional[str], Optional[List[Article]]]:
        """
        Check for potential date range conflicts before article creation with improved validation.

        Args:
            target_date: The publication date to check for conflicts

        Returns:
            Tuple containing:
            - bool: Whether there is a conflict
            - str: Description of the conflict if any
            - List[Article]: List of conflicting articles if any
        """
        if target_date.tzinfo is None:
            target_date = pytz.UTC.localize(target_date)

        # Ensure the date is a Monday
        if target_date.weekday() != 0:
            days_until_monday = (7 - target_date.weekday()) % 7
            suggested_date = target_date + timedelta(days=days_until_monday)
            return True, f"Date must be a Monday. Suggested date: {suggested_date.strftime('%Y-%m-%d')}", None

        # Calculate week range with microsecond precision
        week_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)

        # Check for future dates
        current_date = datetime.now(pytz.UTC)
        if week_end > current_date:
            return True, "Cannot create articles with future dates", None

        try:
            # Use a transaction to ensure consistency
            with db.session.begin_nested():
                # Lock the articles table for the date check
                existing_articles = Article.query.filter(
                    db.or_(
                        # Direct overlap: Article's date falls within our week
                        db.and_(
                            Article.publication_date >= week_start,
                            Article.publication_date <= week_end
                        ),
                        # Indirect overlap: Article's week range overlaps with our week
                        db.and_(
                            Article.publication_date <= week_end,
                            Article.publication_date + timedelta(days=6) >= week_start
                        )
                    )
                ).with_for_update().all()

                if existing_articles:
                    conflicting_dates = [
                        f"{article.publication_date.strftime('%Y-%m-%d')} (ID: {article.id})"
                        for article in existing_articles
                    ]
                    error_msg = (
                        f"Found {len(existing_articles)} existing article(s) for week of "
                        f"{week_start.strftime('%Y-%m-%d')}: {', '.join(conflicting_dates)}"
                    )
                    return True, error_msg, existing_articles

                return False, None, None

        except Exception as e:
            logger.error(f"Error checking date range conflicts: {str(e)}")
            return True, f"Error checking date conflicts: {str(e)}", None

    def check_for_generating_articles(self) -> bool:
        """Check if any articles are currently being generated with improved timeout."""
        try:
            generating_articles = Article.query.filter_by(status='generating').all()
            if generating_articles:
                current_time = datetime.now(pytz.UTC)
                logger.warning(f"Found {len(generating_articles)} articles in generating status")

                # Cleanup any stale generating articles older than 5 minutes
                cleaned_count = 0
                for article in generating_articles:
                    if not article.published_date or (current_time - article.published_date > timedelta(minutes=5)):
                        logger.warning(f"Found stale generating article {article.id}, resetting to draft status")
                        article.status = 'draft'
                        cleaned_count += 1

                if cleaned_count > 0:
                    try:
                        db.session.commit()
                        logger.info(f"Reset {cleaned_count} stale articles to draft status")
                    except Exception as e:
                        logger.error(f"Error committing cleanup changes: {str(e)}")
                        db.session.rollback()

                # Return True if there are any non-stale generating articles
                active_articles = [
                    article for article in generating_articles
                    if article.published_date and (current_time - article.published_date <= timedelta(minutes=5))
                ]
                return len(active_articles) > 0
            return False
        except Exception as e:
            logger.error(f"Error checking for generating articles: {str(e)}")
            return False

    def _generate_content_hash(self, title: str, content: str) -> str:
        """Generate a more robust hash of the article content for duplicate detection."""
        import hashlib
        # Ensure title is a string and normalize it
        safe_title = str(title).strip().lower() if title else ""
        # Normalize content
        safe_content = content.strip() if content else ""
        # Create a unique combination including publication date
        combined_content = f"{safe_title}|{safe_content}"
        return hashlib.sha256(combined_content.encode()).hexdigest()

    def check_for_duplicate_content(self, title: str, content: str) -> tuple[bool, Optional[Article]]:
        """Check if an article with similar content already exists using improved criteria."""
        try:
            # Ensure title is a string and normalize it
            safe_title = str(title).strip().lower() if title else ""
            content_hash = self._generate_content_hash(safe_title, content)

            # Check for exact content match using hash
            existing_article = Article.query.filter_by(content_hash=content_hash).first()
            if existing_article:
                logger.warning(f"Found duplicate article with matching content hash: {existing_article.id}")
                return True, existing_article

            # Additional check for similar titles
            similar_title_articles = Article.query.filter(
                Article.title.ilike(f"%{safe_title}%")
            ).all()

            for article in similar_title_articles:
                # If titles are very similar, consider it a duplicate
                if self._calculate_title_similarity(safe_title, article.title.lower()) > 0.8:
                    logger.warning(f"Found duplicate article with similar title: {article.id}")
                    return True, article

            return False, None

        except Exception as e:
            logger.error(f"Error checking for duplicate content: {str(e)}")
            return False, None

    def _calculate_title_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two titles using Levenshtein distance."""
        from difflib import SequenceMatcher
        return SequenceMatcher(None, title1, title2).ratio()

    def _generate_article_content(self, repo_content: Dict, forum_summary: Optional[str]) -> str:
        """Generates the article content using OpenAI."""
        try:
            # Convert datetime objects to strings in repo_content
            def serialize_content(content):
                if isinstance(content, dict):
                    return {k: serialize_content(v) for k, v in content.items()}
                elif isinstance(content, list):
                    return [serialize_content(item) for item in content]
                elif isinstance(content, datetime):
                    return content.isoformat()
                return content

            serialized_content = serialize_content(repo_content)

            messages = [
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

                    Title requirements:
                    - Create simple, clear titles that describe the main improvements
                    - Write titles that anyone can understand
                    - Combine multiple key changes in plain language
                    - DO NOT include dates or week references
                    - DO NOT use technical terms, parentheses, or quotation marks
                    - Example: "Making Smart Contracts Better and Network Updates"
                    - Example: "Network Speed Improvements and Better Security"

                    Required sections:
                    1. A clear, simple title following the above format
                    2. A detailed overview (at least 700 characters)
                    3. Repository updates (start with 'Repository Updates:')
                    4. Technical highlights (start with 'Technical Highlights:')
                    5. Next Steps (start with 'Next Steps:')"""
                },
                {
                    "role": "user",
                    "content": f"""Create a simple, easy-to-understand update about Ethereum development for the week.
                    Remember:
                    - Create clear, simple titles without technical terms
                    - Explain the main improvements in plain language
                    - Avoid technical jargon and quotation marks in titles
                    - Use everyday language
                    - Make complex ideas easy to understand
                    - Focus on real-world benefits
                    - Keep explanations clear and simple
                    - Include clear 'Repository Updates:', 'Technical Highlights:', and 'Next Steps:' sections

                    Here are the technical updates to analyze:
                    {json.dumps(serialized_content, indent=2)}
                    Forum Summary: {forum_summary or ''}"""
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
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Error generating article content: {str(e)}", exc_info=True)
            raise


    def generate_weekly_summary(self, github_content: List[Dict], publication_date: Optional[datetime] = None) -> Optional[Article]:
        """Generate a weekly summary article from GitHub content with improved duplicate prevention."""
        if not github_content:
            logger.error("No GitHub content provided for summary generation")
            raise ValueError("GitHub content is required for summary generation")

        try:
            # Check if any articles are currently being generated
            if self.check_for_generating_articles():
                logger.warning("Another article is currently being generated. Skipping this generation.")
                return None

            # Validate and prepare the publication date
            if publication_date:
                if not isinstance(publication_date, datetime):
                    publication_date = datetime.fromisoformat(str(publication_date))
                if publication_date.tzinfo is None:
                    publication_date = pytz.UTC.localize(publication_date)
            else:
                # Get the most recent Monday if no date specified
                current_date = datetime.now(pytz.UTC)
                publication_date = self.get_available_date_range(current_date)

            # Check for date range conflicts with FOR UPDATE lock
            has_conflict, error_msg, _ = self.check_date_range_conflicts(publication_date)
            if has_conflict:
                logger.warning(error_msg)
                return None

            logger.info(f"Starting article generation for date: {publication_date}")

            # Calculate the week range with microsecond precision
            week_start = publication_date.replace(hour=0, minute=0, second=0, microsecond=0)
            week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)

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

            # Generate content and check for duplicates
            content = self._generate_article_content(repo_content, forum_summary)
            sections = self._extract_content_sections(content)

            # Begin transaction with row-level locking
            with db.session.begin_nested():
                try:
                    # Double-check for duplicates with row locks
                    has_duplicate, duplicate_article = self.check_for_duplicate_content(sections['title'], content)
                    if has_duplicate:
                        logger.warning(f"Duplicate content detected. Similar to article ID: {duplicate_article.id if duplicate_article else 'Unknown'}")
                        return None

                    # Format the content as HTML
                    article_content = self._format_article_content({
                        'title': sections['title'],
                        'brief_summary': sections['brief_summary'],
                        'repository_updates': [{'summary': update} for update in sections['repo_updates']],
                        'technical_highlights': [{'description': highlight} for highlight in sections['tech_highlights']],
                        'next_steps': sections['next_steps'],
                        'forum_summary': forum_summary
                    })

                    # Create and save the article with content hash
                    article = Article(
                        title=sections['title'],
                        content=article_content,
                        publication_date=publication_date,
                        status='generating',
                        published_date=datetime.now(pytz.UTC),
                        forum_summary=forum_summary if forum_summary else forum_error,
                        content_hash=self._generate_content_hash(sections['title'], article_content)
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

                    # Final check for conflicts before committing
                    has_conflict, _, _ = self.check_date_range_conflicts(publication_date)
                    if has_conflict:
                        logger.warning("Date range conflict detected during final check, rolling back")
                        return None

                    # Update status to published and commit
                    article.status = 'published'
                    db.session.commit()

                    logger.info(f"Successfully created article: {article.title}")
                    return article

                except Exception as e:
                    logger.error(f"Error saving article: {str(e)}")
                    db.session.rollback()
                    return None

        except Exception as e:
            logger.error(f"Error in generate_weekly_summary: {str(e)}", exc_info=True)
            db.session.rollback()
            raise

    def get_available_date_range(self, target_date: Optional[datetime] = None) -> datetime:
        """
        Find the next available date range for article creation.

        Args:
            target_date: Optional starting point for the search

        Returns:
            datetime: The next available Monday that doesn't have a conflict
        """
        if target_date is None:
            target_date = datetime.now(pytz.UTC)

        if target_date.tzinfo is None:
            target_date = pytz.UTC.localize(target_date)

        # Start from the given date and find the next available Monday
        current_date = target_date
        max_attempts = 52  # Don't look more than a year back
        attempts = 0

        while attempts < max_attempts:
            # If not a Monday, move to the previous Monday
            days_since_monday = current_date.weekday()
            if days_since_monday != 0:
                current_date = current_date - timedelta(days=days_since_monday)

            # Check for conflicts
            has_conflict, _, _ = self.check_date_range_conflicts(current_date)

            if not has_conflict:
                return current_date

            # Move to the previous week
            current_date = current_date - timedelta(days=7)
            attempts += 1

        raise ValueError("Could not find an available date range within the last year")