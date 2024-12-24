import logging
import re
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Union
from bs4 import BeautifulSoup
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
            self.forum_base_url = "https://ethereum-magicians.org/c/protocol-calls/63.json"
            api_key = os.environ.get('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable is not set")

            self.openai = OpenAI(api_key=api_key)
            self.model = "gpt-4"  # Using a more powerful model for better summaries
            self.max_retries = 5
            self.base_delay = 5  # Increased initial delay to 5 seconds
            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (compatible; EthDevWatch/1.0; +https://ethdevwatch.replit.app)'
            })
            self.last_api_call = 0
            self.min_time_between_calls = 2  # Minimum seconds between calls
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

    def fetch_forum_discussions(self, week_date: datetime) -> List[Dict]:
        """Fetch forum discussions for a specific week using the JSON API."""
        try:
            start_date, end_date = self._get_week_boundaries(week_date)
            logger.info(f"Starting forum discussions fetch for week of {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
            fetch_start_time = time.time()

            # Use the JSON API endpoint with retries
            response = self._retry_with_backoff(
                self.session.get,
                self.forum_base_url,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            initial_fetch_time = time.time() - fetch_start_time
            logger.info(f"Initial forum data fetch completed in {initial_fetch_time:.2f} seconds")

            discussions = []
            if 'topic_list' in data and 'topics' in data['topic_list']:
                topics = data['topic_list']['topics']
                total_topics = len(topics)
                logger.info(f"Found {total_topics} topics to process")

                for index, topic in enumerate(topics, 1):
                    try:
                        process_start_time = time.time()
                        logger.info(f"Processing topic {index}/{total_topics} ({(index/total_topics)*100:.1f}%)")

                        created_at = topic.get('created_at')
                        if not created_at:
                            logger.debug(f"No created_at field for topic: {topic.get('title', 'Unknown')}")
                            continue

                        try:
                            post_date = datetime.strptime(created_at, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=pytz.UTC)
                        except ValueError:
                            try:
                                post_date = datetime.strptime(created_at, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=pytz.UTC)
                            except ValueError as e:
                                logger.error(f"Error parsing date {created_at}: {str(e)}")
                                continue

                        if start_date <= post_date <= end_date:
                            topic_id = topic.get('id')
                            slug = topic.get('slug', str(topic_id))
                            topic_url = f"https://ethereum-magicians.org/t/{slug}/{topic_id}.json"

                            logger.debug(f"Fetching details for topic: {topic.get('title', 'Unknown')}")
                            topic_fetch_start = time.time()

                            # Fetch full topic content with retries
                            topic_response = self._retry_with_backoff(
                                self.session.get,
                                topic_url,
                                timeout=30
                            )
                            topic_response.raise_for_status()
                            topic_data = topic_response.json()

                            topic_fetch_time = time.time() - topic_fetch_start
                            logger.debug(f"Topic details fetched in {topic_fetch_time:.2f} seconds")

                            if 'post_stream' in topic_data and 'posts' in topic_data['post_stream']:
                                first_post = topic_data['post_stream']['posts'][0]
                                content = first_post.get('cooked', '')

                                # Clean HTML content
                                content_soup = BeautifulSoup(content, 'lxml')
                                clean_content = content_soup.get_text(strip=True)

                                # Truncate content if too long
                                if len(clean_content) > 5000:
                                    clean_content = clean_content[:5000] + "..."

                                discussions.append({
                                    'title': topic.get('title', ''),
                                    'content': clean_content,
                                    'url': f"https://ethereum-magicians.org/t/{slug}/{topic_id}",
                                    'date': post_date
                                })
                                process_time = time.time() - process_start_time
                                logger.info(f"Successfully added discussion: {topic.get('title', '')} (processed in {process_time:.2f} seconds)")

                    except Exception as e:
                        logger.error(f"Error processing topic: {str(e)}", exc_info=True)
                        continue

            total_fetch_time = time.time() - fetch_start_time
            logger.info(f"Successfully fetched {len(discussions)} relevant discussions in {total_fetch_time:.2f} seconds")
            return discussions

        except Exception as e:
            logger.error(f"Error fetching forum discussions: {str(e)}", exc_info=True)
            return []

    def _wait_for_rate_limit(self):
        """Implement rate limiting for API calls."""
        now = time.time()
        time_since_last_call = now - self.last_api_call
        if time_since_last_call < self.min_time_between_calls:
            sleep_time = self.min_time_between_calls - time_since_last_call
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        self.last_api_call = time.time()

    def _retry_with_backoff(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Execute a function with exponential backoff retry logic."""
        max_retries = self.max_retries
        base_delay = self.base_delay
        last_error = None

        for attempt in range(max_retries):
            try:
                if attempt > 0:  # Add delay before retries (not first attempt)
                    delay = min(300, (base_delay * (2 ** attempt)))  # Cap at 5 minutes
                    logger.info(f"Retry attempt {attempt + 1}, waiting {delay} seconds...")
                    time.sleep(delay)

                self._wait_for_rate_limit()  # Apply rate limiting before each attempt
                return func(*args, **kwargs)

            except Exception as e:
                last_error = e
                logger.error(f"Attempt {attempt + 1} failed: {str(e)}", exc_info=True)

                if attempt == max_retries - 1:
                    logger.error(f"Max retries ({max_retries}) exceeded. Final error: {str(e)}")
                    raise

        if last_error:
            raise last_error

    def summarize_discussions(self, discussions: List[Dict]) -> Optional[str]:
        """Generate a summary of forum discussions using OpenAI."""
        if not discussions:
            logger.warning("No discussions provided for summarization")
            return None

        try:
            logger.info("Starting forum discussions summarization")
            formatted_discussions = []
            for disc in discussions:
                formatted_discussions.append(
                    f"Title: {disc['title']}\nDate: {disc['date'].strftime('%Y-%m-%d')}\n"
                    f"URL: {disc['url']}\nContent: {disc['content'][:1000]}..."
                )

            combined_text = "\n\n---\n\n".join(formatted_discussions)

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

                    Format the output in HTML, using appropriate tags for structure."""
                },
                {
                    "role": "user",
                    "content": f"Summarize these Ethereum Magicians forum discussions:\n\n{combined_text}"
                }
            ]

            logger.info("Sending request to OpenAI for forum discussion summary")

            for attempt in range(self.max_retries):
                try:
                    self._wait_for_rate_limit()
                    response = self.openai.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=0.7,
                        max_tokens=1000
                    )

                    summary = response.choices[0].message.content.strip()
                    logger.info("Successfully generated forum discussion summary")

                    if not summary.startswith('<'):
                        summary = f'<div class="forum-discussion-summary">{summary}</div>'

                    return summary

                except Exception as e:
                    if attempt == self.max_retries - 1:
                        logger.error(f"Failed to generate summary after {self.max_retries} attempts: {str(e)}")
                        return None

                    delay = min(300, self.base_delay * (2 ** attempt))
                    logger.warning(f"Summary generation attempt {attempt + 1} failed: {str(e)}. Retrying in {delay} seconds...")
                    time.sleep(delay)

        except Exception as e:
            logger.error(f"Error generating forum discussion summary: {str(e)}", exc_info=True)
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