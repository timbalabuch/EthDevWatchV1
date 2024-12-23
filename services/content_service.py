import logging
from datetime import datetime
from openai import OpenAI
import json
from app import db
from models import Article, Source

logger = logging.getLogger(__name__)

class ContentService:
    def __init__(self):
        self.openai = OpenAI()
        # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
        # do not change this unless explicitly requested by the user
        self.model = "gpt-4o"

    def generate_weekly_summary(self, github_content):
        """Generate a weekly summary using ChatGPT"""
        try:
            # Prepare content for GPT
            content_text = json.dumps(github_content, indent=2)
            
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

            response = self.openai.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            summary_data = json.loads(response.choices[0].message.content)
            
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
            
            return article

        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            db.session.rollback()
            raise
