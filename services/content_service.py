import json
import logging
import os
import random
import time
from datetime import datetime, timedelta

import pytz
from openai import OpenAI, RateLimitError

from app import db
from models import Article, Source

logger = logging.getLogger(__name__)

class ContentService:
    def __init__(self):
        try:
            api_key = os.environ.get('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable is not set")

            self.openai = OpenAI(api_key=api_key)
            self.model = "gpt-4"  # Fixed model name
            self.max_retries = 5
            self.base_delay = 1
            logger.info("ContentService initialized with OpenAI client")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            raise

    def _retry_with_exponential_backoff(self, func, *args, **kwargs):
        """Execute a function with exponential backoff retry logic"""
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except RateLimitError as e:
                last_exception = e
                if attempt == self.max_retries - 1:
                    logger.error(f"Max retries ({self.max_retries}) exceeded: {str(e)}")
                    raise
                delay = min(600, (self.base_delay * (2 ** attempt)) + (random.random() * 5))
                logger.warning(f"Rate limit hit, retrying in {delay} seconds (attempt {attempt + 1}/{self.max_retries})")
                time.sleep(delay)
            except Exception as e:
                logger.error(f"Unexpected error in attempt {attempt + 1}: {str(e)}")
                last_exception = e
                if attempt == self.max_retries - 1:
                    raise last_exception
                delay = min(300, (self.base_delay * (2 ** attempt)) + (random.random() * 2))
                logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)

    def organize_content_by_repository(self, github_content):
        """Organize GitHub content by repository and type"""
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

    def generate_weekly_summary(self, github_content, publication_date=None):
        """Generate a weekly summary article from GitHub content"""
        if not github_content:
            logger.error("No GitHub content provided for summary generation")
            raise ValueError("GitHub content is required for summary generation")

        try:
            current_date = datetime.now(pytz.UTC)

            if publication_date:
                if not isinstance(publication_date, datetime):
                    publication_date = datetime.fromisoformat(str(publication_date))
                if publication_date.tzinfo is None:
                    publication_date = pytz.UTC.localize(publication_date)
            else:
                # Get the Monday of the current week
                days_since_monday = current_date.weekday()
                publication_date = current_date - timedelta(days=days_since_monday)
                publication_date = publication_date.replace(hour=0, minute=0, second=0, microsecond=0)
                publication_date = pytz.UTC.localize(publication_date)

            # Check if an article already exists for this week
            monday = publication_date - timedelta(days=publication_date.weekday())
            monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
            sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

            existing_article = Article.query.filter(
                Article.publication_date >= monday,
                Article.publication_date <= sunday
            ).first()

            if existing_article:
                logger.info(f"Article already exists for week of {monday.strftime('%Y-%m-%d')}")
                return existing_article

            logger.info(f"Generating article with publication date: {publication_date}")

            # Organize content by repository
            repo_content = self.organize_content_by_repository(github_content)

            if not repo_content:
                logger.warning("No content found to summarize")
                return None

            week_str = publication_date.strftime("%Y-%m-%d")
            logger.info(f"Generating content for week of {week_str}")

            # Create repository summaries
            repo_summaries = []
            for repo, content in repo_content.items():
                summary = {
                    'repository': repo,
                    'total_issues': len(content['issues']),
                    'total_commits': len(content['commits']),
                    'sample_issues': [
                        {'title': issue['title'], 'url': issue['url']}
                        for issue in content['issues'][:3]
                    ],
                    'sample_commits': [
                        {'title': commit['title'], 'url': commit['url']}
                        for commit in content['commits'][:3]
                    ]
                }
                repo_summaries.append(summary)

            # Generate the technical summary
            messages = [
                {
                    "role": "system",
                    "content": """You are an expert in Ethereum ecosystem development. Create a comprehensive weekly summary 
                    of development activities across multiple Ethereum repositories. Focus on:

                    1. Core protocol development (ethereum/pm)
                    2. EIP proposals and changes (ethereum/EIPs)
                    3. API specifications (ethereum/execution-apis)
                    4. Implementation specifications (ethereum/execution-specs, ethereum/consensus-specs)

                    Structure the response as JSON with the following sections:
                    1. title: An engaging title highlighting key developments
                    2. brief_summary: 2-3 sentences capturing main updates
                    3. repository_updates: Array of updates from each repository
                    4. technical_highlights: Key technical changes and their impact
                    5. next_steps: Expected next steps or ongoing discussions

                    Keep the focus on technical accuracy and ecosystem impact."""
                },
                {
                    "role": "user",
                    "content": f"""Generate a comprehensive Ethereum ecosystem development update for the week of {week_str}.

                    Repository Activity Summary:
                    {json.dumps(repo_summaries, indent=2)}"""
                }
            ]

            response = self._retry_with_exponential_backoff(
                self.openai.chat.completions.create,
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=2000
            )

            if not response or not hasattr(response, 'choices') or not response.choices:
                raise ValueError("Invalid response from OpenAI API")

            try:
                summary_data = json.loads(response.choices[0].message.content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse OpenAI response as JSON: {str(e)}")
                raise ValueError("Invalid JSON response from OpenAI")

            content = self._format_article_content(summary_data, None)
            article = Article(
                title=summary_data["title"],
                content=content,
                publication_date=publication_date,
                status='published',
                published_date=current_date
            )

            # Add sources for each piece of content
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
            logger.error(f"Error generating summary: {str(e)}")
            db.session.rollback()
            raise

    def _format_article_content(self, summary_data, intro_data):
        """Format the article content with proper HTML structure"""
        try:
            article_html = f"""
                <article class="ethereum-article">
                    <div class="article-content mb-4">
                        <p class="lead">{summary_data.get('brief_summary', '')}</p>
                    </div>

                    <div class="repository-updates mb-4">
                        <h2 class="section-title">Repository Updates</h2>
                        {self._format_repository_updates(summary_data.get('repository_updates', []))}
                    </div>

                    <div class="technical-highlights mb-4">
                        <h2 class="section-title">Technical Highlights</h2>
                        {self._format_technical_highlights(summary_data.get('technical_highlights', []))}
                    </div>

                    <div class="next-steps mb-4">
                        <h2 class="section-title">Next Steps</h2>
                        <ul>
                            {''.join(f"<li>{step}</li>" for step in summary_data.get('next_steps', []))}
                        </ul>
                    </div>
                </article>
            """

            logger.info("Generated article HTML length: %d", len(article_html))
            return article_html

        except Exception as e:
            logger.error(f"Error formatting article content: {str(e)}")
            raise

    def _format_repository_updates(self, updates):
        """Format repository updates section"""
        formatted_updates = []
        for update in updates:
            update_html = f"""
                <div class="repository-update mb-3">
                    <h3 class="repository-name">{update.get('repository', '')}</h3>
                    <div class="update-summary">
                        <p>{update.get('summary', '')}</p>
                    </div>
                    <div class="key-changes">
                        <strong>Key Changes:</strong>
                        <ul>
                            {''.join(f"<li>{change}</li>" for change in update.get('changes', []))}
                        </ul>
                    </div>
                </div>
            """
            formatted_updates.append(update_html)
        return '\n'.join(formatted_updates)

    def _format_technical_highlights(self, highlights):
        """Format technical highlights section"""
        formatted_highlights = []
        for highlight in highlights:
            highlight_html = f"""
                <div class="highlight mb-3">
                    <h3>{highlight.get('title', '')}</h3>
                    <p>{highlight.get('description', '')}</p>
                    <div class="highlight-impact">
                        <strong>Impact:</strong>
                        <p>{highlight.get('impact', '')}</p>
                    </div>
                </div>
            """
            formatted_highlights.append(highlight_html)
        return '\n'.join(formatted_highlights)