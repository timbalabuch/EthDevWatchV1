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
            self.model = "gpt-4o"
            self.max_retries = 5
            self.base_delay = 1
            logger.info("ContentService initialized with OpenAI client")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            raise

    def _retry_with_exponential_backoff(self, func, *args, **kwargs):
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

    def generate_weekly_summary(self, github_content, publication_date=None):
        if not github_content:
            logger.error("No GitHub content provided for summary generation")
            raise ValueError("GitHub content is required for summary generation")

        try:
            current_date = datetime.now(pytz.UTC)

            if publication_date:
                if publication_date.tzinfo is None:
                    publication_date = pytz.UTC.localize(publication_date)
                if publication_date > current_date:
                    logger.error(f"Cannot create article with future date: {publication_date}")
                    return None
            else:
                publication_date = current_date - timedelta(days=current_date.weekday())
                publication_date = publication_date.replace(hour=0, minute=0, second=0, microsecond=0)
                publication_date = pytz.UTC.localize(publication_date)

            current_week_content = []
            week_start = publication_date.replace(hour=0, minute=0, second=0, microsecond=0)
            week_end = week_start + timedelta(days=7)

            if week_end > current_date:
                week_end = current_date

            # Organize content by repository
            repo_content = {}
            for item in github_content:
                item_date = item.get('created_at')
                if item_date:
                    if isinstance(item_date, datetime) and item_date.tzinfo is None:
                        item_date = pytz.UTC.localize(item_date)
                    if week_start <= item_date <= week_end:
                        repo = item['repository']
                        if repo not in repo_content:
                            repo_content[repo] = []
                        repo_content[repo].append(item)
                        current_week_content.append(item)

            if not current_week_content:
                logger.warning("No content found for the specified week")
                return None

            week_str = week_start.strftime("%Y-%m-%d")
            logger.info(f"Generating content for week of {week_str}")

            # Create a detailed breakdown of content by repository
            content_summary = []
            for repo, items in repo_content.items():
                content_summary.append(f"{repo}: {len(items)} items ({', '.join(set(item['type'] for item in items))})")

            messages = [
                {
                    "role": "system",
                    "content": """You are an expert in Ethereum ecosystem development. Create a comprehensive weekly summary 
                    of development activities across multiple Ethereum repositories, including:
                    - ethereum/pm: Core protocol meetings and discussions
                    - ethereum/EIPs: Ethereum Improvement Proposals
                    - ethereum/execution-apis: Execution layer API specifications
                    - ethereum/execution-specs: Execution layer specifications
                    - ethereum/consensus-specs: Consensus layer specifications

                    Structure the response as JSON with the following sections:
                    1. title: An engaging title highlighting key developments
                    2. brief_summary: 2-3 sentences capturing main updates
                    3. meetings: Array of meeting summaries from ethereum/pm
                    4. technical_updates: Array of technical changes from specs repositories
                    5. proposals: Array of EIP updates and status changes

                    Include repository attribution for each item."""
                },
                {
                    "role": "user",
                    "content": f"""Generate a comprehensive Ethereum ecosystem development update for the week of {week_str}.
                    Content breakdown:
                    {chr(10).join(content_summary)}"""
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

            content = self._format_article_content(summary_data)
            article = Article(
                title=summary_data["title"],
                content=content,
                publication_date=publication_date,
                status='published',
                published_date=current_date
            )

            for item in current_week_content:
                source = Source(
                    url=item['url'],
                    type='github',
                    title=item.get('title', ''),
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

    def _format_article_content(self, summary_data):
        return f"""
        <div class="article-summary mb-4">
            <p class="lead">{summary_data.get('brief_summary', '')}</p>
        </div>

        <div class="ethereum-updates">
            <div class="meetings-section mb-4">
                <h2 class="section-title">Meeting Summaries</h2>
                {''.join(f'''
                <div class="meeting-card mb-3">
                    <h3>{meeting.get('title', '')}</h3>
                    <div class="meeting-source text-muted mb-2">
                        <small>From {meeting.get('repository', 'ethereum/pm')}</small>
                    </div>
                    <ul class="key-points list-unstyled">
                        {''.join(f'<li class="mb-2">{point}</li>' for point in meeting.get('key_points', []))}
                    </ul>
                    <div class="decisions">
                        <strong>Key Decisions:</strong>
                        <p>{meeting.get('decisions', '')}</p>
                    </div>
                </div>
                ''' for meeting in summary_data.get('meetings', []))}
            </div>

            <div class="technical-section">
                <h2 class="section-title">Technical Updates</h2>
                {''.join(f'''
                <div class="technical-card mb-3">
                    <h3>{update.get('area', '')}</h3>
                    <div class="repository-source text-muted mb-2">
                        <small>From {update.get('repository', 'ethereum/specs')}</small>
                    </div>
                    <div class="changes">
                        <strong>Changes:</strong>
                        <p>{update.get('changes', '')}</p>
                    </div>
                    <div class="impact">
                        <strong>Impact:</strong>
                        <p>{update.get('impact', '')}</p>
                    </div>
                </div>
                ''' for update in summary_data.get('technical_updates', []))}
            </div>

            <div class="proposals-section">
                <h2 class="section-title">EIPs and Proposals</h2>
                {''.join(f'''
                <div class="proposal-card mb-3">
                    <h3>{proposal.get('title', '')}</h3>
                    <div class="repository-source text-muted mb-2">
                        <small>From {proposal.get('repository', 'ethereum/EIPs')}</small>
                    </div>
                    <div class="summary">
                        <p>{proposal.get('summary', '')}</p>
                    </div>
                    <div class="status">
                        <strong>Status:</strong> {proposal.get('status', 'Draft')}
                    </div>
                </div>
                ''' for proposal in summary_data.get('proposals', []))}
            </div>
        </div>
        """