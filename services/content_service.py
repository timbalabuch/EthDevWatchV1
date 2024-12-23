import logging
from datetime import datetime
from openai import OpenAI
import json
from app import db
from models import Article, Source

logger = logging.getLogger(__name__)

class ContentService:
    def __init__(self):
        try:
            self.openai = OpenAI()
            # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
            # do not change this unless explicitly requested by the user
            self.model = "gpt-4o"
            logger.info("ContentService initialized with OpenAI client")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            raise

    def _datetime_handler(self, obj):
        """Handle datetime serialization for JSON"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    def generate_weekly_summary(self, github_content):
        """Generate a weekly summary using ChatGPT"""
        if not github_content:
            logger.error("No GitHub content provided for summary generation")
            raise ValueError("GitHub content is required for summary generation")

        try:
            # Prepare content for GPT
            logger.info("Preparing content for GPT processing")
            content_text = json.dumps(github_content, indent=2, default=self._datetime_handler)

            prompt = f"""
            Generate a comprehensive weekly summary of Ethereum ecosystem developments based on the following data:

            {content_text}

            Format the response as a JSON object with the following structure:
            {{
                "title": "Weekly Ethereum Ecosystem Update - [Current Date]",
                "summary": "Main summary text with key points and developments",
                "highlights": ["Array of key highlights"]
            }}

            Make the content accessible to a general audience while maintaining technical accuracy.
            """

            logger.info("Sending request to OpenAI API")
            response = self.openai.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )

            logger.debug(f"Received response from OpenAI API: {response.choices[0].message.content[:200]}...")

            try:
                summary_data = json.loads(response.choices[0].message.content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse OpenAI response as JSON: {str(e)}")
                logger.debug(f"Raw response content: {response.choices[0].message.content}")
                raise ValueError("Invalid JSON response from OpenAI")

            logger.info("Creating new article with generated content")
            # Create new article
            article = Article(
                title=summary_data["title"],
                content=summary_data["summary"],
                publication_date=datetime.utcnow()
            )

            # Add sources
            for item in github_content:
                source = Source(
                    url=item['url'],
                    type='github',
                    title=item['title'],
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