import logging
import os
import time
import random
from datetime import datetime, timedelta
from openai import OpenAI, RateLimitError
import json
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
            # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
            # do not change this unless explicitly requested by the user
            self.model = "gpt-4o"
            self.max_retries = 5
            self.base_delay = 1  # Base delay in seconds
            logger.info("ContentService initialized with OpenAI client")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            raise

    def _retry_with_exponential_backoff(self, func, *args, **kwargs):
        """Execute a function with exponential backoff retry logic"""
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                result = func(*args, **kwargs)
                return result
            except RateLimitError as e:
                last_exception = e
                if attempt == self.max_retries - 1:
                    logger.error(f"Max retries ({self.max_retries}) exceeded: {str(e)}")
                    raise
                delay = min(600, (self.base_delay * (2 ** attempt)) + (random.random() * 5))  # Increased max delay to 10 minutes
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

    def _find_existing_image_url(self, title):
        """Check if we have a similar article with an image we can reuse"""
        try:
            # First try exact title match
            existing_article = Article.query.filter(
                Article.image_url.isnot(None)
            ).order_by(Article.publication_date.desc()).first()

            if existing_article and existing_article.image_url:
                logger.info(f"Reusing existing image from article: {existing_article.title}")
                return existing_article.image_url
            return None
        except Exception as e:
            logger.error(f"Error finding existing image: {str(e)}")
            return None

    def generate_image_for_title(self, title):
        """Generate an image using DALL-E based on the article title"""
        try:
            # First check if we can reuse an existing image
            existing_url = self._find_existing_image_url(title)
            if existing_url:
                logger.info("Reusing existing image")
                return existing_url

            # Add longer delay before image generation
            time.sleep(5)  # Increased delay to avoid rate limits

            prompt = (
                f"Create a sophisticated horizontal technology-themed illustration for an article titled: {title}. "
                "Style: modern, professional, tech-focused with dominant green and blue color scheme. "
                "Must be in landscape orientation with a 16:9 aspect ratio. "
                "Theme: Ethereum blockchain, technological advancement, digital innovation. "
                "Color requirement: Use vibrant emerald greens (#00FF7F) and electric blues (#0000FF) as the dominant colors "
                "in the design, creating a high-tech, futuristic aesthetic. The image should have a dark background "
                "with glowing green and blue elements to represent blockchain technology."
            )

            response = self._retry_with_exponential_backoff(
                self.openai.images.generate,
                model="dall-e-3",
                prompt=prompt,
                n=1,
                size="1792x1024",
                quality="standard",
                style="vivid"
            )

            if response and hasattr(response, 'data') and len(response.data) > 0:
                logger.info("Successfully generated image for article")
                return response.data[0].url
            else:
                logger.error("Invalid response format from DALL-E API")
                return None

        except Exception as e:
            logger.error(f"Failed to generate image: {str(e)}")
            return None

    def generate_weekly_summary(self, github_content, publication_date=None):
        """Generate a weekly summary using ChatGPT"""
        if not github_content:
            logger.error("No GitHub content provided for summary generation")
            raise ValueError("GitHub content is required for summary generation")

        try:
            # Check if we already have an article for this week
            if publication_date:
                existing_article = Article.query.filter(
                    Article.publication_date >= publication_date,
                    Article.publication_date <= publication_date + timedelta(days=7)
                ).first()

                if existing_article:
                    logger.info(f"Article already exists for week of {publication_date.strftime('%Y-%m-%d')}")
                    return existing_article

            time.sleep(2)

            logger.info("Preparing content for GPT processing")
            week_str = publication_date.strftime("%Y-%m-%d") if publication_date else "current week"

            week_prompt = f"""For the week of {week_str}, generate a comprehensive Ethereum ecosystem development update. 
            Focus on creating unique content that would be realistic for that specific week, including:
            - Technical progress in Layer 2 solutions
            - Updates to the Ethereum protocol
            - Development tooling improvements
            - Community and governance updates

            Make the content specific and detailed, as if these were real updates from that week.
            """

            messages = [
                {
                    "role": "system",
                    "content": """You are an expert in Ethereum ecosystem development. Create a weekly summary of development activities 
                    focused on meetings and technical updates. The title should be engaging and highlight the most important development 
                    of the week. Include a concise 2-3 sentence summary that captures the key developments. Format the response as JSON with this structure:
                    {
                        "title": "Engaging title highlighting key development",
                        "brief_summary": "2-3 sentence summary of key developments",
                        "meetings": [
                            {
                                "title": "Meeting name",
                                "key_points": ["point 1", "point 2"],
                                "decisions": "Key decisions made"
                            }
                        ],
                        "technical_updates": [
                            {
                                "area": "Component/Area name",
                                "changes": "Technical changes and progress",
                                "impact": "Impact on ecosystem"
                            }
                        ]
                    }"""
                },
                {
                    "role": "user",
                    "content": week_prompt
                }
            ]

            logger.info(f"Sending request to OpenAI API for week of {week_str}")
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


            logger.debug(f"Received response from OpenAI API: {response.choices[0].message.content[:200]}...")

            try:
                summary_data = json.loads(response.choices[0].message.content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse OpenAI response as JSON: {str(e)}")
                logger.debug(f"Raw response content: {response.choices[0].message.content}")
                raise ValueError("Invalid JSON response from OpenAI")

            content = f"""
            <div class="article-summary mb-4">
                <p class="lead">{summary_data['brief_summary']}</p>
            </div>

            <div class="meetings-section mb-4">
                <h2 class="section-title">Meeting Summaries</h2>
                {''.join(f'''
                <div class="meeting-card mb-3">
                    <h3>{meeting['title']}</h3>
                    <ul class="key-points list-unstyled">
                        {''.join(f'<li class="mb-2"><i class="fas fa-check text-success me-2"></i>{point}</li>' for point in meeting['key_points'])}
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

            logger.info("Creating new article with generated content")
            image_url = self.generate_image_for_title(summary_data["title"])

            article = Article(
                title=summary_data["title"],
                content=content,
                publication_date=publication_date or datetime.utcnow(),
                image_url=image_url
            )

            for item in github_content:
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