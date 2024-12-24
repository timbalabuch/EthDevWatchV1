import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Union
from bs4 import BeautifulSoup
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
            self.forum_base_url = "https://ethereum-magicians.org/c/protocol-calls/63.json"
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

    def fetch_forum_discussions(self, week_date: datetime) -> List[Dict]:
        """Fetch forum discussions for a specific week using the JSON API."""
        try:
            start_date, end_date = self._get_week_boundaries(week_date)
            logger.info(f"Fetching forum discussions for week of {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

            # Use the JSON API endpoint
            response = self._retry_with_backoff(
                self.session.get,
                self.forum_base_url,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            logger.info("Successfully fetched forum data from API")

            discussions = []
            if 'topic_list' in data and 'topics' in data['topic_list']:
                topics = data['topic_list']['topics']
                logger.info(f"Found {len(topics)} topics in the response")

                for topic in topics:
                    try:
                        # Extract date from the created_at field
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
                            # Fetch full topic content using topic id
                            topic_id = topic.get('id')
                            slug = topic.get('slug', str(topic_id))
                            topic_url = f"https://ethereum-magicians.org/t/{slug}/{topic_id}.json"

                            topic_response = self._retry_with_backoff(
                                self.session.get,
                                topic_url,
                                timeout=30
                            )
                            topic_response.raise_for_status()
                            topic_data = topic_response.json()

                            # Extract content from the first post
                            if 'post_stream' in topic_data and 'posts' in topic_data['post_stream']:
                                first_post = topic_data['post_stream']['posts'][0]
                                content = first_post.get('cooked', '')  # 'cooked' contains the HTML content

                                # Clean HTML content
                                content_soup = BeautifulSoup(content, 'lxml')
                                clean_content = content_soup.get_text(strip=True)

                                # Truncate content if it's too long
                                if len(clean_content) > 5000:
                                    clean_content = clean_content[:5000] + "..."

                                discussions.append({
                                    'title': topic.get('title', ''),
                                    'content': clean_content,
                                    'url': f"https://ethereum-magicians.org/t/{slug}/{topic_id}",
                                    'date': post_date
                                })
                                logger.info(f"Successfully added discussion: {topic.get('title', '')}")

                    except Exception as e:
                        logger.error(f"Error processing topic: {str(e)}", exc_info=True)
                        continue

            logger.info(f"Successfully fetched {len(discussions)} relevant discussions for the week")
            return discussions

        except Exception as e:
            logger.error(f"Error fetching forum discussions: {str(e)}", exc_info=True)
            return []

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
                delay = min(300, (self.base_delay * (2 ** attempt)))  # Cap at 5 minutes
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {delay} seconds...")
                time.sleep(delay)

        if last_error:
            raise last_error

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
            # Generate summary with retries
            for attempt in range(3):  # 3 retries for OpenAI
                try:
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
                    if attempt == 2:  # Last attempt
                        logger.error(f"Error generating forum discussion summary: {str(e)}")
                        return None
                    logger.warning(f"Attempt {attempt + 1} failed: {str(e)}. Retrying...")
                    time.sleep(20)  # Wait longer between OpenAI retries

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