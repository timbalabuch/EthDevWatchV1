import logging
import re
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import requests
import pytz
from bs4 import BeautifulSoup
from openai import OpenAI
import os

logger = logging.getLogger(__name__)

class ForumService:
    """Service for fetching and processing Ethereum forum discussions."""

    def __init__(self):
        """Initialize the ForumService."""
        self.magicians_base_url = "https://ethereum-magicians.org/c/protocol-calls/63.json"
        self.ethresear_base_url = "https://ethresear.ch/c/protocol/16.json"
        self.model = "gpt-4"
        self.max_retries = 5
        self.base_delay = 10
        self.max_delay = 120
        self.last_api_call = 0
        self.min_time_between_calls = 5

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; EthDevWatch/1.0; +https://ethdevwatch.replit.app)'
        })

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

    def fetch_forum_discussions(self, date: datetime) -> List[Dict]:
        """Fetch forum discussions from both Ethereum Magicians and Ethereum Research."""
        magicians_discussions = self._fetch_magicians_discussions(date)
        ethresear_discussions = self._fetch_ethresear_discussions(date)

        return {
            'magicians': self._format_magicians_discussions(magicians_discussions),
            'ethresear': self._format_ethresear_discussions(ethresear_discussions)
        }

    def _fetch_magicians_discussions(self, date: datetime) -> List[Dict]:
        """Fetch discussions from ethereum-magicians.org."""
        try:
            response = self._retry_with_backoff(
                self.session.get,
                self.magicians_base_url,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            discussions = []
            if 'topic_list' in data and 'topics' in data['topic_list']:
                for topic in data['topic_list']['topics']:
                    if self._is_in_date_range(topic.get('created_at'), date):
                        discussion = self._process_magicians_topic(topic)
                        if discussion:
                            discussions.append(discussion)

            return discussions
        except Exception as e:
            logger.error(f"Error fetching Ethereum Magicians discussions: {str(e)}")
            return []

    def _fetch_ethresear_discussions(self, date: datetime) -> List[Dict]:
        """Fetch discussions from ethresear.ch."""
        try:
            response = self._retry_with_backoff(
                self.session.get,
                self.ethresear_base_url,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            discussions = []
            if 'topic_list' in data and 'topics' in data['topic_list']:
                for topic in data['topic_list']['topics']:
                    if self._is_in_date_range(topic.get('created_at'), date):
                        discussion = self._process_ethresear_topic(topic)
                        if discussion:
                            discussions.append(discussion)

            return discussions
        except Exception as e:
            logger.error(f"Error fetching Ethereum Research discussions: {str(e)}")
            return []

    def _process_magicians_topic(self, topic: Dict) -> Optional[Dict]:
        """Process a single Ethereum Magicians topic."""
        try:
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

            if 'post_stream' in topic_data and 'posts' in topic_data['post_stream']:
                first_post = topic_data['post_stream']['posts'][0]
                content = first_post.get('cooked', '')

                # Clean HTML content
                content_soup = BeautifulSoup(content, 'lxml')
                clean_content = content_soup.get_text(strip=True)

                return {
                    'title': topic.get('title', ''),
                    'content': clean_content[:500] + ('...' if len(clean_content) > 500 else ''),
                    'url': f"https://ethereum-magicians.org/t/{slug}/{topic_id}",
                    'date': topic.get('created_at'),
                    'source': 'ethereum-magicians.org'
                }
        except Exception as e:
            logger.error(f"Error processing Magicians topic: {str(e)}")
        return None

    def _process_ethresear_topic(self, topic: Dict) -> Optional[Dict]:
        """Process a single Ethereum Research topic."""
        try:
            topic_id = topic.get('id')
            slug = topic.get('slug', str(topic_id))
            topic_url = f"https://ethresear.ch/t/{slug}/{topic_id}.json"

            topic_response = self._retry_with_backoff(
                self.session.get,
                topic_url,
                timeout=30
            )
            topic_response.raise_for_status()
            topic_data = topic_response.json()

            if 'post_stream' in topic_data and 'posts' in topic_data['post_stream']:
                first_post = topic_data['post_stream']['posts'][0]
                content = first_post.get('cooked', '')

                # Clean HTML content
                content_soup = BeautifulSoup(content, 'lxml')
                clean_content = content_soup.get_text(strip=True)

                return {
                    'title': topic.get('title', ''),
                    'content': clean_content[:500] + ('...' if len(clean_content) > 500 else ''),
                    'url': f"https://ethresear.ch/t/{slug}/{topic_id}",
                    'date': topic.get('created_at'),
                    'source': 'ethresear.ch'
                }
        except Exception as e:
            logger.error(f"Error processing Research topic: {str(e)}")
        return None

    def _format_magicians_discussions(self, discussions: List[Dict]) -> str:
        """Format Ethereum Magicians discussions into HTML."""
        if not discussions:
            return None

        html_parts = []
        for disc in discussions:
            html_parts.append(f"""
                <div class="forum-discussion-item mb-4">
                    <h4 class="discussion-title mb-2">{disc['title']}</h4>
                    <div class="meta-info mb-2">
                        <span class="date">{disc['date']}</span>
                        <span class="badge bg-info ms-2">ethereum-magicians.org</span>
                    </div>
                    <div class="forum-content mb-3">{disc['content']}</div>
                    <a href="{disc['url']}" target="_blank" class="forum-link btn btn-outline-info btn-sm">
                        Read full discussion →
                    </a>
                </div>
            """)

        return '\n'.join(html_parts)

    def _format_ethresear_discussions(self, discussions: List[Dict]) -> str:
        """Format Ethereum Research discussions into HTML."""
        if not discussions:
            return None

        html_parts = []
        for disc in discussions:
            html_parts.append(f"""
                <div class="forum-discussion-item ethresearch-item mb-4">
                    <h4 class="discussion-title mb-2">{disc['title']}</h4>
                    <div class="meta-info mb-2">
                        <span class="date">{disc['date']}</span>
                        <span class="badge bg-info ms-2">ethresear.ch</span>
                    </div>
                    <div class="forum-content mb-3">{disc['content']}</div>
                    <a href="{disc['url']}" target="_blank" class="forum-link btn btn-outline-info btn-sm">
                        Read full discussion →
                    </a>
                </div>
            """)

        return '\n'.join(html_parts)

    def _is_in_date_range(self, date_str: str, target_date: datetime) -> bool:
        """Check if a date string falls within the week of the target date."""
        try:
            date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=pytz.UTC)
            week_start = target_date - timedelta(days=target_date.weekday())
            week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
            return week_start <= date <= week_end
        except ValueError:
            return False

    def _retry_with_backoff(self, func, *args, **kwargs):
        """Execute a function with exponential backoff retry logic."""
        for attempt in range(self.max_retries):
            try:
                self._wait_for_rate_limit()
                response = func(*args, **kwargs)
                return response
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                delay = min(self.max_delay, self.base_delay * (2 ** attempt))
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {delay} seconds...")
                time.sleep(delay)

    def _wait_for_rate_limit(self):
        """Implement rate limiting for API calls."""
        now = time.time()
        time_since_last_call = now - self.last_api_call
        if time_since_last_call < self.min_time_between_calls:
            sleep_time = self.min_time_between_calls - time_since_last_call
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        self.last_api_call = time.time()