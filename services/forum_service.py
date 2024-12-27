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
        self.ethresear_base_url = "https://ethresear.ch"
        self.ethresear_categories = [
            "latest.json",  # Get latest posts across all categories
            "c/protocol/16.json",
            "c/rollups/45.json"  # Updated category for L2/rollups
        ]
        self.model = "gpt-4"
        self.max_retries = 3  # Reduced retries to avoid long waits
        self.base_delay = 20  # Increased base delay for rate limiting
        self.max_delay = 60
        self.last_api_call = 0
        self.min_time_between_calls = 10  # Increased minimum time between calls

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

    def _format_forum_content(self, content: str, source: str, title: str, date: datetime, url: str) -> str:
        """Format forum content with consistent styling."""
        try:
            # Clean content
            content_soup = BeautifulSoup(content, 'lxml')
            clean_content = content_soup.get_text(strip=True)
            brief_content = clean_content[:500] + ('...' if len(clean_content) > 500 else '')

            source_class = 'ethresearch-item' if 'ethresear.ch' in source else 'magicians-item'

            formatted_content = f"""
            <div class="forum-discussion-item {source_class} mb-4">
                <h4 class="discussion-title mb-2">{title.replace('html', '').replace('HTML', '')}</h4>
                <div class="meta-info mb-2">
                    <span class="date">{date.strftime('%Y-%m-%d')}</span>
                    <span class="badge bg-info ms-2">{source}</span>
                </div>
                <div class="forum-content mb-3">{brief_content}</div>
                <a href="{url}" 
                   target="_blank" 
                   class="forum-link btn btn-outline-info btn-sm">
                    Read full discussion →
                </a>
            </div>
            """

            logger.debug(f"Successfully formatted forum content for {title}")
            return formatted_content

        except Exception as e:
            logger.error(f"Error formatting forum content: {str(e)}")
            return ""

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

            all_discussions = []
            processed_topics = set()  # Track processed topics to avoid duplicates

            # Fetch from multiple categories
            for category in self.ethresear_categories:
                category_url = f"{self.ethresear_base_url}/{category}"
                logger.info(f"Fetching discussions from category: {category}")

                try:
                    # Add delay between category fetches
                    if len(all_discussions) > 0:
                        time.sleep(self.min_time_between_calls)

                    response = self._retry_with_backoff(
                        self.session.get,
                        category_url,
                        timeout=60
                    )

                    if response.status_code == 404:
                        logger.warning(f"Category not found: {category}, skipping...")
                        continue

                    response.raise_for_status()
                    data = response.json()

                    if not data or 'topic_list' not in data:
                        logger.warning(f"Invalid response format from ethresear.ch for category: {category}")
                        continue

                    topics = data['topic_list'].get('topics', [])
                    logger.info(f"Found {len(topics)} topics in category {category}")

                    for topic in topics:
                        try:
                            topic_id = topic.get('id')
                            if topic_id in processed_topics:  # Skip if already processed
                                continue
                            processed_topics.add(topic_id)

                            created_at = topic.get('created_at')
                            if not created_at:
                                continue

                            try:
                                # Try different date formats
                                for date_format in ['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ']:
                                    try:
                                        post_date = datetime.strptime(created_at, date_format).replace(tzinfo=pytz.UTC)
                                        break
                                    except ValueError:
                                        continue
                                else:
                                    continue
                            except Exception as e:
                                logger.debug(f"Date parsing error for {created_at}: {str(e)}")
                                continue

                            if start_date <= post_date <= end_date:
                                slug = topic.get('slug', str(topic_id))
                                topic_url = f"{self.ethresear_base_url}/t/{slug}/{topic_id}.json"

                                # Add delay between topic fetches
                                time.sleep(self.min_time_between_calls)

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

                                    formatted_content = self._format_forum_content(
                                        content=content,
                                        source='ethresear.ch',
                                        title=topic.get('title', ''),
                                        date=post_date,
                                        url=f"{self.ethresear_base_url}/t/{slug}/{topic_id}"
                                    )
                                    if formatted_content:
                                        all_discussions.append({
                                            'title': topic.get('title', ''),
                                            'content': formatted_content,
                                            'url': f"{self.ethresear_base_url}/t/{slug}/{topic_id}",
                                            'date': post_date,
                                            'source': 'ethresear.ch'
                                        })
                                        logger.info(f"Successfully added ethresear.ch discussion: {topic.get('title', '')}")

                        except Exception as e:
                            logger.error(f"Error processing ethresear.ch topic: {str(e)}", exc_info=True)
                            continue

                except requests.RequestException as e:
                    logger.error(f"Failed to fetch ethresear.ch data for category {category}: {str(e)}")
                    continue

            total_fetch_time = time.time() - fetch_start_time
            logger.info(f"Successfully fetched {len(all_discussions)} relevant discussions from ethresear.ch in {total_fetch_time:.2f} seconds")
            return all_discussions

        except Exception as e:
            logger.error(f"Error fetching ethresear.ch discussions: {str(e)}", exc_info=True)
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
        last_error = None
        for attempt in range(self.max_retries):
            try:
                self._wait_for_rate_limit()
                response = func(*args, **kwargs)

                if isinstance(response, requests.Response):
                    if response.status_code == 404:
                        return response  # Return 404 response without retrying
                    response.raise_for_status()
                    logger.debug(f"Request successful - Status: {response.status_code}")
                return response

            except Exception as e:
                last_error = e
                delay = min(self.max_delay, self.base_delay * (2 ** attempt))

                if isinstance(e, requests.RequestException) and hasattr(e, 'response'):
                    logger.error(f"Request failed - Status: {e.response.status_code}")
                    if e.response.status_code == 404:
                        return e.response  # Return 404 response without retrying

                if attempt < self.max_retries - 1:
                    logger.warning(f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    logger.error(f"All {self.max_retries} attempts failed")

        raise last_error

    def summarize_forum_discussions(self, discussions: List[Dict], source: str) -> Optional[str]:
        """Generate a summary of forum discussions for a specific source using OpenAI."""
        if not discussions:
            logger.warning(f"No discussions provided for summarization from {source}")
            return None

        if not self.openai:
            logger.warning("OpenAI client not initialized - returning raw discussion content")
            return self._format_raw_discussions(discussions)

        try:
            logger.info(f"Starting {source} forum discussions summarization")
            formatted_discussions = []
            for disc in discussions:
                content_soup = BeautifulSoup(disc['content'], 'lxml')
                clean_content = content_soup.get_text(strip=True)
                formatted_discussions.append(
                    f"Title: {disc['title']}\n"
                    f"Date: {disc['date'].strftime('%Y-%m-%d')}\n"
                    f"URL: {disc['url']}\n"
                    f"Content Summary: {clean_content[:1000]}..."
                )

            combined_text = "\n\n---\n\n".join(formatted_discussions)

            messages = [
                {
                    "role": "system",
                    "content": f"""You are an expert in Ethereum protocol discussions. 
                    Summarize the key points from {source} forum discussions in a clear, 
                    accessible way. Focus on:
                    1. Main topics discussed
                    2. Important decisions or consensus reached
                    3. Notable technical proposals
                    Keep the summary concise and use plain language.

                    Format your response as a clean HTML section with:
                    - A section header for {source}
                    - Key points in bullet points
                    - No full HTML document tags (html, head, body)
                    - Use div with appropriate classes for styling"""
                },
                {
                    "role": "user",
                    "content": f"Summarize these {source} discussions from the past week:\n\n{combined_text}"
                }
            ]

            logger.info(f"Sending request to OpenAI for {source} forum discussion summary")

            try:
                self._wait_for_rate_limit()
                response = self.openai.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1000
                )

                summary = response.choices[0].message.content.strip()
                logger.info(f"Successfully generated {source} forum discussion summary")

                # Ensure proper HTML structure without document tags
                if not summary.startswith('<div'):
                    summary = f"""
                    <div class="forum-summary {source.lower().replace('.', '-')}">
                        <h3 class="forum-source-title mb-3">{source} Summary</h3>
                        {summary}
                    </div>
                    """

                return summary

            except Exception as e:
                logger.error(f"OpenAI API error: {str(e)}")
                return self._format_raw_discussions(discussions)

        except Exception as e:
            logger.error(f"Error generating {source} forum discussion summary: {str(e)}", exc_info=True)
            return self._format_raw_discussions(discussions)

    def get_weekly_forum_summary(self, date: datetime) -> Optional[str]:
        """Get a summary of forum discussions for a specific week."""
        try:
            logger.info(f"Getting forum summary for week of {date.strftime('%Y-%m-%d')}")

            # Fetch discussions from both sources
            em_discussions = self.fetch_forum_discussions(date)
            ethresear_discussions = self.fetch_ethresear_discussions(date)

            if not em_discussions and not ethresear_discussions:
                logger.warning("No forum discussions found for the specified week")
                return None

            logger.info(f"Found {len(em_discussions)} Ethereum Magicians discussions and {len(ethresear_discussions)} Ethereum Research discussions")

            # Generate summaries for each source
            em_summary = None
            ethresear_summary = None

            if em_discussions:
                em_summary = self.summarize_forum_discussions(em_discussions, "Ethereum Magicians")
                time.sleep(self.min_time_between_calls)  # Add delay between summary generations

            if ethresear_discussions:
                ethresear_summary = self.summarize_forum_discussions(ethresear_discussions, "Ethereum Research")

            # Combine summaries and discussions
            content_parts = []

            # Add summaries section if any exists
            if em_summary or ethresear_summary:
                content_parts.append('<div class="forum-summaries mb-4">')
                content_parts.append('<h2 class="forum-summaries-title mb-3">Forum Discussion Summaries</h2>')
                if em_summary:
                    content_parts.append(em_summary)
                if ethresear_summary:
                    content_parts.append(ethresear_summary)
                content_parts.append('</div>')

            # Add detailed discussions section
            if em_discussions or ethresear_discussions:
                content_parts.append('<div class="forum-discussions mt-4">')
                content_parts.append('<h2 class="forum-discussions-title mb-3">Recent Forum Discussions</h2>')

                if em_discussions:
                    content_parts.append('<div class="ethereum-magicians-section mb-4">')
                    content_parts.append('<h3 class="section-title">Ethereum Magicians Discussions</h3>')
                    content_parts.extend(disc['content'] for disc in em_discussions)
                    content_parts.append('</div>')

                if ethresear_discussions:
                    content_parts.append('<div class="ethereum-research-section mb-4">')
                    content_parts.append('<h3 class="section-title">Ethereum Research Discussions</h3>')
                    content_parts.extend(disc['content'] for disc in ethresear_discussions)
                    content_parts.append('</div>')

                content_parts.append('</div>')

            if not content_parts:
                logger.warning("No content generated for forum summary")
                return None

            # Combine all parts with proper container
            summary = '<div class="forum-discussions-container">' + '\n'.join(content_parts) + '</div>'
            logger.info("Successfully generated forum summary")
            return summary

        except Exception as e:
            logger.error(f"Error getting weekly forum summary: {str(e)}", exc_info=True)
            return None

    def _format_raw_discussions(self, discussions: List[Dict]) -> str:
        """Format discussions without OpenAI summarization."""
        formatted_content = []
        for disc in discussions:
            content_soup = BeautifulSoup(disc['content'], 'lxml')
            clean_content = content_soup.get_text(strip=True)[:500]
            formatted_content.append(f"""
                <div class="forum-discussion-item">
                    <h4>{disc['title']}</h4>
                    <p>Source: {disc['source']}</p>
                    <p>Date: {disc['date'].strftime('%Y-%m-%d')}</p>
                    <div class="forum-content">{clean_content}...</div>
                    <a href="{disc['url']}" target="_blank" class="forum-link">
                        Read more →
                    </a>
                </div>
            """)

        return f"""
        <div class="forum-discussion-summary">
            <div class="alert alert-info">
                Summaries are temporarily unavailable. Showing raw discussion content.
            </div>
            {''.join(formatted_content)}
        </div>
        """

    def fetch_forum_discussions(self, week_date: datetime) -> List[Dict]:
        """Fetch forum discussions from Ethereum Magicians for a specific week."""
        try:
            start_date, end_date = self._get_week_boundaries(week_date)
            logger.info(f"Starting forum discussions fetch for week of {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
            self._wait_for_rate_limit()  # Ensure we respect rate limits
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

                                formatted_content = self._format_forum_content(
                                    content=content,
                                    source='ethereum-magicians.org',
                                    title=topic.get('title', ''),
                                    date=post_date,
                                    url=f"https://ethereum-magicians.org/t/{slug}/{topic_id}"
                                )
                                if formatted_content:
                                    discussions.append({
                                        'title': topic.get('title', ''),
                                        'content': formatted_content,
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
                content_soup = BeautifulSoup(disc['content'], 'lxml')
                clean_content = content_soup.get_text(strip=True)
                formatted_discussions.append(
                    f"Title: {disc['title']}\nSource: {disc['source']}\n"
                    f"Date: {disc['date'].strftime('%Y-%m-%d')}\n"
                    f"URL: {disc['url']}\nContent: {clean_content[:1000]}..."
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
                logger.error(f"OpenAI API error: {str(e)}")
                return self._format_raw_discussions(discussions)

        except Exception as e:
            logger.error(f"Error generating forum discussion summary: {str(e)}", exc_info=True)
            return None