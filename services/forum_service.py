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
    """Service for fetching and processing Ethereum forum discussions."""

    def __init__(self):
        """Initialize the ForumService."""
        self.forum_base_url = "https://ethereum-magicians.org/c/protocol-calls/63.json"
        self.ethresear_base_url = "https://ethresear.ch/c/protocol/16.json"
        self.model = "gpt-4"
        self.max_retries = 5
        self.base_delay = 5  # Initial delay in seconds
        self.max_delay = 60  # Maximum delay in seconds
        self.last_api_call = 0
        self.min_time_between_calls = 2
        
        # Initialize session with custom headers
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; EthDevWatch/1.0; +https://ethdevwatch.replit.app)'
        })

        # Initialize OpenAI client with graceful fallback
        try:
            api_key = os.environ.get('OPENAI_API_KEY')
            if not api_key:
                logger.warning("OPENAI_API_KEY not set - summarization features will be disabled")
                self.openai = None
            else:
                self.openai = OpenAI(api_key=api_key)
                logger.info("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            self.openai = None

        logger.info("ForumService initialized successfully")

    def _get_week_boundaries(self, date: datetime) -> tuple[datetime, datetime]:
        """Get the start and end dates for a given week."""
        if date.tzinfo is None:
            date = pytz.UTC.localize(date)
        start_date = date - timedelta(days=date.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=6, hours=23, minutes=59, seconds=59)
        return start_date, end_date

    def fetch_ethresear_discussions(self, week_date: datetime) -> List[Dict]:
        """Fetch forum discussions from ethresear.ch for a specific week."""
        try:
            start_date, end_date = self._get_week_boundaries(week_date)
            logger.info(f"Starting ethresear.ch discussions fetch for week of {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
            fetch_start_time = time.time()

            try:
                response = self._retry_with_backoff(
                    self.session.get,
                    self.ethresear_base_url,
                    timeout=60  # Increased timeout
                )
                response.raise_for_status()
                data = response.json()
                
                if not data or 'topic_list' not in data:
                    logger.error("Invalid response format from ethresear.ch")
                    logger.debug(f"Response content: {str(data)[:1000]}")
                    return []
                    
            except requests.RequestException as e:
                logger.error(f"Failed to fetch ethresear.ch data: {str(e)}")
                if hasattr(e, 'response'):
                    logger.error(f"Status code: {e.response.status_code}")
                    logger.error(f"Response text: {e.response.text[:1000]}")
                return []
            except ValueError as e:
                logger.error(f"Invalid JSON from ethresear.ch: {str(e)}")
                return []
            initial_fetch_time = time.time() - fetch_start_time
            logger.info(f"Initial ethresear.ch data fetch completed in {initial_fetch_time:.2f} seconds")

            discussions = []
            if 'topic_list' in data and 'topics' in data['topic_list']:
                topics = data['topic_list']['topics']
                total_topics = len(topics)
                logger.info(f"Found {total_topics} topics to process from ethresear.ch")

                for index, topic in enumerate(topics, 1):
                    try:
                        process_start_time = time.time()
                        logger.info(f"Processing ethresear.ch topic {index}/{total_topics} ({(index/total_topics)*100:.1f}%)")

                        # Validate required topic fields
                        required_fields = ['created_at', 'id', 'title']
                        missing_fields = [field for field in required_fields if not topic.get(field)]
                        
                        if missing_fields:
                            logger.warning(f"Skipping topic due to missing fields: {', '.join(missing_fields)}")
                            continue
                            
                        created_at = topic['created_at']
                        
                        try:
                            # Try different date formats
                            for date_format in ['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ']:
                                try:
                                    post_date = datetime.strptime(created_at, date_format).replace(tzinfo=pytz.UTC)
                                    break
                                except ValueError:
                                    continue
                            else:
                                logger.error(f"Could not parse date {created_at} in any known format")
                                continue
                                
                        except Exception as e:
                            logger.error(f"Unexpected error parsing date {created_at}: {str(e)}")
                            continue

                        if start_date <= post_date <= end_date:
                            topic_id = topic.get('id')
                            slug = topic.get('slug', str(topic_id))
                            topic_url = f"https://ethresear.ch/t/{slug}/{topic_id}.json"

                            logger.debug(f"Fetching details for ethresear.ch topic: {topic.get('title', 'Unknown')}")
                            topic_fetch_start = time.time()

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
                                
                                # Create proper forum discussion format
                                # Parse and clean content
                                content_soup = BeautifulSoup(content, 'lxml')
                                
                                # Remove script and style elements
                                for element in content_soup.find_all(['script', 'style']):
                                    element.decompose()
                                
                                # Format content with proper structure
                                formatted_content = f"""
                                <div class="forum-discussion-item ethresearch-item">
                                    <h4 class="discussion-title">{topic.get('title', '')}</h4>
                                    <div class="meta-info">
                                        <span class="date">{post_date.strftime('%Y-%m-%d')}</span>
                                        <span class="source">ethresear.ch</span>
                                    </div>
                                    <div class="forum-content">{str(content_soup)}</div>
                                    <a href="https://ethresear.ch/t/{topic.get('slug')}/{topic.get('id')}" 
                                       target="_blank" 
                                       class="forum-link btn btn-outline-info btn-sm mt-2">
                                        Read full discussion on ethresear.ch →
                                    </a>
                                </div>
                                """

                                discussions.append({
                                    'title': topic.get('title', ''),
                                    'content': formatted_content,
                                    'url': f"https://ethresear.ch/t/{slug}/{topic_id}",
                                    'date': post_date,
                                    'source': 'ethresear.ch'
                                })
                                process_time = time.time() - process_start_time
                                logger.info(f"Successfully added ethresear.ch discussion: {topic.get('title', '')} (processed in {process_time:.2f} seconds)")

                    except Exception as e:
                        logger.error(f"Error processing ethresear.ch topic: {str(e)}", exc_info=True)
                        continue

            total_fetch_time = time.time() - fetch_start_time
            logger.info(f"Successfully fetched {len(discussions)} relevant discussions from ethresear.ch in {total_fetch_time:.2f} seconds")
            return discussions

        except Exception as e:
            logger.error(f"Error fetching ethresear.ch discussions: {str(e)}", exc_info=True)
            return []

    def fetch_forum_discussions(self, week_date: datetime) -> List[Dict]:
        """Fetch forum discussions from Ethereum Magicians for a specific week."""
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

                        # Validate required topic fields
                        required_fields = ['created_at', 'id', 'title']
                        missing_fields = [field for field in required_fields if not topic.get(field)]
                        
                        if missing_fields:
                            logger.warning(f"Skipping topic due to missing fields: {', '.join(missing_fields)}")
                            continue
                            
                        created_at = topic['created_at']
                        
                        try:
                            # Try different date formats
                            for date_format in ['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ']:
                                try:
                                    post_date = datetime.strptime(created_at, date_format).replace(tzinfo=pytz.UTC)
                                    break
                                except ValueError:
                                    continue
                            else:
                                logger.error(f"Could not parse date {created_at} in any known format")
                                continue
                                
                        except Exception as e:
                            logger.error(f"Unexpected error parsing date {created_at}: {str(e)}")
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
                                    'date': post_date,
                                    'source': 'ethereum-magicians.org'
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
        for attempt in range(self.max_retries):
            try:
                self._wait_for_rate_limit()
                response = func(*args, **kwargs)
                
                # Log successful response details
                if isinstance(response, requests.Response):
                    logger.debug(f"Request successful - Status: {response.status_code}")
                return response

            except (requests.RequestException, Exception) as e:
                # Calculate delay with exponential backoff
                delay = min(self.max_delay, self.base_delay * (2 ** attempt))
                
                # Log detailed error information
                logger.error(f"Attempt {attempt + 1}/{self.max_retries} failed")
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Error message: {str(e)}")
                
                if isinstance(e, requests.RequestException) and hasattr(e, 'response'):
                    logger.error(f"Status code: {e.response.status_code}")
                    logger.error(f"Response headers: {dict(e.response.headers)}")
                    logger.error(f"Response text: {e.response.text[:1000]}")

                if attempt < self.max_retries - 1:
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    logger.error(f"Max retries ({self.max_retries}) exceeded")
                    raise

        raise Exception("Retry logic failed to return or raise")

    def summarize_discussions(self, discussions: List[Dict]) -> Optional[str]:
        """Generate a summary of forum discussions using OpenAI."""
        if not discussions:
            logger.warning("No discussions provided for summarization")
            return None
            
        if not self.openai:
            logger.warning("OpenAI client not initialized - returning raw discussion content")
            return self._format_raw_discussions(discussions)

        try:
            logger.info("Starting forum discussions summarization")
            formatted_discussions = []
            for disc in discussions:
                formatted_discussions.append(
                    f"Title: {disc['title']}\nSource: {disc['source']}\n"
                    f"Date: {disc['date'].strftime('%Y-%m-%d')}\n"
                    f"URL: {disc['url']}\nContent: {disc['content'][:1000]}..."
                )

            combined_text = "\n\n---\n\n".join(formatted_discussions)

            messages = [
                {
                    "role": "system",
                    "content": """You are an expert in Ethereum protocol discussions. 
                    Summarize the key points from Ethereum forum discussions in a clear, 
                    accessible way. Focus on:
                    1. Main topics discussed
                    2. Important decisions or consensus reached
                    3. Notable technical proposals
                    Keep the summary concise and use plain language.

                    Format the output in HTML, using appropriate tags for structure."""
                },
                {
                    "role": "user",
                    "content": f"Summarize these Ethereum forum discussions:\n\n{combined_text}"
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

            # Fetch discussions from both sources
            em_discussions = self.fetch_forum_discussions(date)
            ethresear_discussions = self.fetch_ethresear_discussions(date)

            # Combine discussions from both sources
            all_discussions = em_discussions + ethresear_discussions

            if not all_discussions:
                logger.warning("No forum discussions found for the specified week")
                return None

            logger.info(f"Generating summary for {len(all_discussions)} discussions")
            summary = self.summarize_discussions(all_discussions)

            if not summary:
                logger.warning("Failed to generate summary from forum discussions")
                return None

            logger.info("Successfully generated forum summary")
            return summary

        except Exception as e:
            logger.error(f"Error getting weekly forum summary: {str(e)}", exc_info=True)
            return None
    def _format_raw_discussions(self, discussions: List[Dict]) -> str:
        """Format discussions without OpenAI summarization."""
        formatted_content = []
        for disc in discussions:
            formatted_content.append(f"""
                <div class="forum-discussion-item">
                    <h4>{disc['title']}</h4>
                    <p>Source: {disc['source']}</p>
                    <p>Date: {disc['date'].strftime('%Y-%m-%d')}</p>
                    <div class="forum-content">{disc['content'][:500]}...</div>
                    <a href="{disc['url']}" target="_blank" class="forum-link">
                        Read more →
                    </a>
                </div>
            """)
        
        return '<div class="forum-discussion-summary">' + ''.join(formatted_content) + '</div>'
