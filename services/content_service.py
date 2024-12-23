import logging
import os
from datetime import datetime
from openai import OpenAI
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
            logger.info("ContentService initialized with OpenAI client")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            raise

    def generate_weekly_summary(self, github_content):
        """Generate a weekly summary using ChatGPT"""
        if not github_content:
            logger.error("No GitHub content provided for summary generation")
            raise ValueError("GitHub content is required for summary generation")

        try:
            # Prepare content for GPT
            logger.info("Preparing content for GPT processing")
            content_json = json.dumps(github_content, default=str)

            # System prompt for consistent formatting
            messages = [
                {
                    "role": "system",
                    "content": """You are an expert in Ethereum ecosystem development. Create a weekly summary of development activities 
                    focused on meetings and technical updates. Format the response as JSON with this structure:
                    {
                        "title": "Weekly Ethereum Development Update - [Date]",
                        "summary": "Brief overview",
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
                    "content": f"Analyze and summarize this GitHub content:\n\n{content_json}"
                }
            ]

            logger.info("Sending request to OpenAI API")
            response = self.openai.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=2000
            )

            logger.debug(f"Received response from OpenAI API: {response.choices[0].message.content[:200]}...")

            try:
                summary_data = json.loads(response.choices[0].message.content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse OpenAI response as JSON: {str(e)}")
                logger.debug(f"Raw response content: {response.choices[0].message.content}")
                raise ValueError("Invalid JSON response from OpenAI")

            # Format the content with improved HTML structure
            content = f"""
            <div class="article-summary mb-4">
                <p class="lead">{summary_data['summary']}</p>
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
            # Create new article
            article = Article(
                title=summary_data["title"],
                content=content,
                publication_date=datetime.utcnow()
            )

            # Add sources
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