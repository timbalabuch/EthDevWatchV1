import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Union
from bs4 import BeautifulSoup, Tag
import time
import requests
import pytz
from openai import OpenAI
import os

logger = logging.getLogger(__name__)

class ForumService:
    """Service for fetching and processing Ethereum Magicians forum discussions."""

    def __init__(self):
        """Initialize the ForumService."""
        try:
            self.forum_base_url = "https://ethereum-magicians.org/c/protocol-calls/63"
            api_key = os.environ.get('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable is not set")

            self.openai = OpenAI(api_key=api_key)
            self.model = "gpt-4"  # Using a more powerful model for better summaries
            self.max_retries = 3
            self.base_delay = 1
            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (compatible; EthDevWatch/1.0; +https://ethdevwatch.replit.app)'
            })
            logger.info("ForumService initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ForumService: {str(e)}")
            raise

    def _get_week_boundaries(self, date: datetime) -> tuple[datetime, datetime]:
        """Get the start and end dates for a given week."""
        if date.tzinfo is None:
            date = pytz.UTC.localize(date)
        start_date = date - timedelta(days=date.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=6, hours=23, minutes=59, seconds=59)
        return start_date, end_date

    def _extract_date_from_forum_post(self, post_element: Union[Tag, BeautifulSoup]) -> Optional[datetime]:
        """Extract date from a forum post element."""
        try:
            date_elem = post_element.select_one('.post-date, .topic-date')
            if not date_elem:
                logger.debug("No date element found in post")
                return None

            if not date_elem.has_attr('title'):
                logger.debug("Date element has no title attribute")
                return None

            date_str = date_elem['title']
            try:
                return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S%z')
            except ValueError as e:
                logger.error(f"Error parsing date string '{date_str}': {str(e)}")
                return None

        except Exception as e:
            logger.error(f"Error extracting date from forum post: {str(e)}")
            return None

    def _retry_with_backoff(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Execute a function with exponential backoff retry logic."""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt == self.max_retries - 1:
                    logger.error(f"Max retries ({self.max_retries}) exceeded: {str(e)}")
                    raise
                delay = min(300, (self.base_delay * (2 ** attempt)))
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {delay} seconds...")
                time.sleep(delay)

        if last_error:
            raise last_error

    def fetch_forum_discussions(self, week_date: datetime) -> List[Dict]:
        """Fetch forum discussions for a specific week."""
        try:
            start_date, end_date = self._get_week_boundaries(week_date)
            logger.info(f"Fetching forum discussions for week of {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

            # Download the forum page
            logger.info(f"Sending request to {self.forum_base_url}")
            response = self._retry_with_backoff(
                self.session.get,
                self.forum_base_url,
                timeout=30
            )
            response.raise_for_status()
            logger.info(f"Received response with status code: {response.status_code}")

            # Parse HTML content
            soup = BeautifulSoup(response.text, 'lxml')
            discussions = []

            # Find all topic elements
            topics = soup.select('.topic-list-item')
            logger.info(f"Found {len(topics)} topics on the page")

            for topic in topics:
                try:
                    # Extract date
                    post_date = self._extract_date_from_forum_post(topic)
                    if post_date:
                        logger.debug(f"Found post with date: {post_date}")

                    if post_date and start_date <= post_date <= end_date:
                        # Extract title and content
                        title_elem = topic.select_one('.title')
                        title = title_elem.get_text(strip=True) if title_elem else ''

                        # Get topic URL
                        topic_url = None
                        topic_link = title_elem.find('a') if title_elem else None
                        if topic_link and topic_link.has_attr('href'):
                            topic_url = topic_link['href']
                            logger.debug(f"Processing topic: {title} with URL: {topic_url}")

                        if topic_url:
                            # Fetch full topic content
                            full_url = f"https://ethereum-magicians.org{topic_url}"
                            logger.debug(f"Fetching full content from: {full_url}")
                            topic_response = self._retry_with_backoff(
                                self.session.get,
                                full_url,
                                timeout=30
                            )
                            topic_response.raise_for_status()

                            topic_soup = BeautifulSoup(topic_response.text, 'lxml')
                            content_elem = topic_soup.select_one('.topic-body')
                            content = content_elem.get_text(strip=True) if content_elem else ''

                            discussions.append({
                                'title': title,
                                'content': content,
                                'url': full_url,
                                'date': post_date
                            })
                            logger.info(f"Successfully added discussion: {title}")

                except Exception as e:
                    logger.error(f"Error processing topic: {str(e)}", exc_info=True)
                    continue

            logger.info(f"Successfully fetched {len(discussions)} relevant discussions for the week")
            return discussions

        except Exception as e:
            logger.error(f"Error fetching forum discussions: {str(e)}", exc_info=True)
            return []

    def summarize_discussions(self, discussions: List[Dict]) -> Optional[str]:
        """Generate a summary of forum discussions using OpenAI."""
        if not discussions:
            logger.warning("No discussions provided for summarization")
            return None

        try:
            logger.info("Starting forum discussions summarization")
            # Prepare discussions text
            formatted_discussions = []
            for disc in discussions:
                formatted_discussions.append(
                    f"Title: {disc['title']}\nDate: {disc['date'].strftime('%Y-%m-%d')}\n"
                    f"URL: {disc['url']}\nContent: {disc['content'][:1000]}..."
                )

            combined_text = "\n\n---\n\n".join(formatted_discussions)

            # Create prompt for OpenAI
            messages = [
                {
                    "role": "system",
                    "content": """You are an expert in Ethereum protocol discussions. 
                    Summarize the key points from Ethereum Magicians forum discussions in a clear, 
                    accessible way. Focus on:
                    1. Main topics discussed
                    2. Important decisions or consensus reached
                    3. Notable technical proposals
                    Keep the summary concise and use plain language.

                    Format the output in HTML, using appropriate tags for structure.
                    For example:
                    <div class="discussion-point">
                        <h3>[Topic Title]</h3>
                        <p>[Summary of discussion]</p>
                    </div>"""
                },
                {
                    "role": "user",
                    "content": f"Summarize these Ethereum Magicians forum discussions:\n\n{combined_text}"
                }
            ]

            logger.info("Sending request to OpenAI for forum discussion summary")
            # Generate summary
            response = self.openai.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )

            summary = response.choices[0].message.content.strip()
            logger.info("Successfully generated forum discussion summary")

            # If the summary doesn't include HTML tags, wrap it
            if not summary.startswith('<'):
                summary = f'<div class="forum-discussion-summary">{summary}</div>'

            return summary

        except Exception as e:
            logger.error(f"Error generating forum discussion summary: {str(e)}")
            return None

    def get_weekly_forum_summary(self, date: datetime) -> Optional[str]:
        """Get a summary of forum discussions for a specific week."""
        try:
            logger.info(f"Getting forum summary for week of {date.strftime('%Y-%m-%d')}")
            discussions = self.fetch_forum_discussions(date)

            if not discussions:
                logger.warning("No forum discussions found for the specified week")
                return None

            logger.info(f"Generating summary for {len(discussions)} discussions")
            summary = self.summarize_discussions(discussions)
            if not summary:
                logger.warning("Failed to generate summary from forum discussions")
                return None

            logger.info("Successfully generated forum summary")
            return summary

        except Exception as e:
            logger.error(f"Error getting weekly forum summary: {str(e)}", exc_info=True)
            return None