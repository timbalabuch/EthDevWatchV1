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

            for item in github_content:
                item_date = item.get('created_at')
                if item_date:
                    if isinstance(item_date, datetime) and item_date.tzinfo is None:
                        item_date = pytz.UTC.localize(item_date)
                    if week_start <= item_date <= week_end:
                        current_week_content.append(item)

            if not current_week_content:
                logger.warning("No content found for the specified week")
                return None

            week_str = week_start.strftime("%Y-%m-%d")
            logger.info(f"Generating content for week of {week_str}")

            messages = [
                {
                    "role": "system",
                    "content": """You are an expert in Ethereum ecosystem development. Create a weekly summary of development activities 
                    focused on meetings and technical updates. The title should be engaging and highlight the most important development 
                    of the week. Include a concise 2-3 sentence summary that captures the key developments. Format the response as JSON."""
                },
                {
                    "role": "user",
                    "content": f"For the week of {week_str}, generate a comprehensive Ethereum ecosystem development update."
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
                <p class="lead">{summary_data['brief_summary']}</p>
            </div>

            <div class="meetings-section mb-4">
                <h2 class="section-title">Meeting Summaries</h2>
                {''.join(f'''
                <div class="meeting-card mb-3">
                    <h3>{meeting['title']}</h3>
                    <ul class="key-points list-unstyled">
                        {''.join(f'<li class="mb-2">{point}</li>' for point in meeting['key_points'])}
                    </ul>
                    <div class="decisions">
                        <strong>Key Decisions:</strong>
                        <p>{meeting['decisions']}</p>
                    </div>
                </div>
                ''' for meeting in summary_data.get('meetings', []))}
            </div>

            <div class="technical-section">
                <h2 class="section-title">Technical Updates</h2>
                {''.join(f'''
                <div class="technical-card mb-3">
                    <h3>{update['area']}</h3>
                    <div class="changes">
                        <strong>Changes:</strong>
                        <p>{update['changes']}</p>
                    </div>
                    <div class="impact">
                        <strong>Impact:</strong>
                        <p>{update['impact']}</p>
                    </div>
                </div>
                ''' for update in summary_data.get('technical_updates', []))}
            </div>
            """