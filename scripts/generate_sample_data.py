import sys
import os
from datetime import datetime, timedelta
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from services.github_service import GitHubService
from services.content_service import ContentService

def generate_sample_articles():
    github_service = GitHubService()
    content_service = ContentService()
    
    # Get real GitHub content
    github_content = github_service.fetch_recent_content()
    
    # Generate 5 articles for past weeks
    with app.app_context():
        for week in range(5):
            # Set publication date to past weeks
            publication_date = datetime.utcnow() - timedelta(weeks=week+1)
            
            try:
                article = content_service.generate_weekly_summary(github_content)
                # Update the publication date
                article.publication_date = publication_date
                db.session.commit()
                print(f"Generated article for week {week+1}: {article.title}")
            except Exception as e:
                print(f"Error generating article for week {week+1}: {str(e)}")
                db.session.rollback()

if __name__ == "__main__":
    generate_sample_articles()
