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
            self.model = "gpt-4"
            self.max_retries = 5
            self.base_delay = 1
            logger.info("ContentService initialized with OpenAI client")
        except Exception as e:
            logger.error(f"Failed to initialize ContentService: {str(e)}")
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

    def _clean_title(self, title):
        """Clean and format the article title"""
        title = title.replace('Title:', '').strip()
        title = title.replace('"', '').replace("'", '').strip()
        if ':' in title and not any(x in title for x in ['Update', 'Progress', 'Development', 'Enhancement']):
            title = title.split(':', 1)[1].strip()
        return title

    def _extract_content_sections(self, content):
        """Extract different sections from the content"""
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
            'brief_summary': brief_summary,
            'repo_updates': repo_updates,
            'tech_highlights': tech_highlights,
            'next_steps': next_steps
        }

    def _format_article_content(self, summary_data):
        """Format the article content with proper HTML structure"""
        try:
            article_html = f"""
                <article class="ethereum-article">
                    <div class="article-content mb-4">
                        {summary_data.get('brief_summary', '')}
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
            logger.info("Generated article HTML length: %d", len(article_html))
            return article_html

        except Exception as e:
            logger.error(f"Error formatting article content: {str(e)}")
            raise

    def _format_repository_updates(self, updates):
        """Format repository updates section"""
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

    def _format_technical_highlights(self, highlights):
        """Format technical highlights section"""
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

    def generate_weekly_summary(self, github_content, publication_date=None):
        """Generate a weekly summary article from GitHub content"""
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

            # Calculate week's end date
            end_date = publication_date + timedelta(days=6, hours=23, minutes=59, seconds=59)

            week_str = publication_date.strftime("%Y-%m-%d")
            logger.info(f"Generating content for week of {week_str}")

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

            # Generate the article content using OpenAI
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
                    "content": f"""Create a simple, easy-to-understand update about Ethereum development for the week of {week_str}.
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

            # Ensure minimum length for brief summary
            if len(sections['brief_summary']) < 700:
                logger.warning(f"Brief summary too short ({len(sections['brief_summary'])} chars), regenerating...")
                messages[0]["content"] += "\n\nIMPORTANT: Your explanation MUST be at least 700 characters long."
                response = self._retry_with_exponential_backoff(
                    self.openai.chat.completions.create,
                    model=self.model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2000
                )
                content = response.choices[0].message.content
                sections = self._extract_content_sections(content)

            # Format the content as HTML
            content = self._format_article_content({
                'title': sections['title'],
                'brief_summary': sections['brief_summary'],
                'repository_updates': [{'summary': update} for update in sections['repo_updates']],
                'technical_highlights': [{'description': highlight} for highlight in sections['tech_highlights']],
                'next_steps': sections['next_steps']
            })

            article = Article(
                title=sections['title'],
                content=content,
                publication_date=publication_date,
                status='published',
                published_date=current_date
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