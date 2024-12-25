import logging
import re
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
import pytz
from bs4 import BeautifulSoup

# Configure logging (adjust as needed for your application)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Set the desired logging level
handler = logging.StreamHandler() # Or file handler for production
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    publication_date = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(pytz.UTC))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    sources = db.relationship('Source', backref='article', lazy=True)
    forum_summary = db.Column(db.Text)  # New field for forum discussions

    # Publishing workflow columns
    status = db.Column(db.String(20), nullable=False, default='draft')  # draft, scheduled, published
    scheduled_publish_date = db.Column(db.DateTime)
    published_date = db.Column(db.DateTime)

    @property
    def is_published(self):
        return self.status == 'published'

    @property
    def is_scheduled(self):
        return self.status == 'scheduled'

    def publish(self):
        self.status = 'published'
        self.published_date = datetime.now(pytz.UTC)
        db.session.commit()

    def schedule(self, publish_date):
        self.status = 'scheduled'
        self.scheduled_publish_date = publish_date
        db.session.commit()

    @property
    def brief_summary(self):
        """Extract brief summary from content."""
        if not self.content:
            return None
        try:
            soup = BeautifulSoup(self.content, 'lxml')
            # Look for the overview content div
            overview = soup.find('div', class_='overview-section')
            if overview:
                # Get the actual content div inside overview section
                overview_content = overview.find('div', class_='overview-content')
                if overview_content:
                    text = overview_content.get_text(strip=True)
                    # Limit to 350 characters
                    return text[:350] + ('...' if len(text) > 350 else '')
            return None
        except Exception as e:
            print(f"Error extracting brief summary: {e}")
            return None

    @property
    def magicians_discussions(self):
        """Extract Ethereum Magicians discussions."""
        if not self.forum_summary:
            error_msg = "Content is still being fetched from ethereum-magicians.org. Please check back later."
            logger.info(error_msg)
            return f'<div class="alert alert-info"><i class="fas fa-sync-alt"></i> {error_msg}</div>'
        try:
            logger.info("Processing magicians discussions from forum summary")
            soup = BeautifulSoup(self.forum_summary, 'lxml')
            
            # Look specifically for ethereum-magicians content
            discussions = []
            content_div = soup.find('div', class_='forum-discussion-summary')
            if content_div:
                for disc in content_div.find_all('div', class_='forum-discussion-item'):
                    if 'ethereum-magicians.org' in str(disc):
                        discussions.append(disc)
            
            if discussions:
                return ''.join(str(disc) for disc in discussions)
            
            error_msg = "No discussions found on ethereum-magicians.org for this time period"
            logger.warning(error_msg)
            return f'<div class="alert alert-info"><i class="fas fa-info-circle"></i> {error_msg}</div>'
            
        except Exception as e:
            error_msg = f"Error retrieving ethereum-magicians.org discussions: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return f'<div class="alert alert-danger"><i class="fas fa-exclamation-triangle"></i> {error_msg}</div>'
        except Exception as e:
            logger.error(f"Error extracting magicians discussions: {e}", exc_info=True)
            return None

    @property
    def ethresearch_discussions(self):
        """Extract Ethereum Research discussions."""
        if not self.forum_summary:
            error_msg = "Content is still being fetched from ethresear.ch. Please check back later."
            logger.info(error_msg)
            return f'<div class="alert alert-info"><i class="fas fa-sync-alt"></i> {error_msg}</div>'
        try:
            logger.info("Processing research discussions from forum summary")
            soup = BeautifulSoup(self.forum_summary, 'lxml')
            
            # Look specifically for ethresear.ch content
            discussions = []
            content_div = soup.find('div', class_='forum-discussion-summary')
            if content_div:
                for disc in content_div.find_all('div', class_='forum-discussion-item'):
                    if 'ethresear.ch' in str(disc):
                        discussions.append(disc)
            
            if discussions:
                return ''.join(str(disc) for disc in discussions)
            
            error_msg = "No discussions found on ethresear.ch for this time period"
            logger.warning(error_msg)
            return f'<div class="alert alert-info"><i class="fas fa-info-circle"></i> {error_msg}</div>'
            
        except Exception as e:
            error_msg = f"Error retrieving ethresear.ch discussions: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return f'<div class="alert alert-danger"><i class="fas fa-exclamation-triangle"></i> {error_msg}</div>'

    @property
    def repository_updates(self):
        """Extract repository updates from content."""
        if not self.content:
            return None
        soup = BeautifulSoup(self.content, 'lxml')
        updates = soup.find('div', class_='repository-updates')
        return str(updates) if updates else None

    @property
    def technical_highlights(self):
        """Extract technical highlights from content."""
        if not self.content:
            return None
        soup = BeautifulSoup(self.content, 'lxml')
        highlights = soup.find('div', class_='technical-highlights')
        return str(highlights) if highlights else None

    @property
    def next_steps(self):
        """Extract next steps from content."""
        if not self.content:
            return []
        soup = BeautifulSoup(self.content, 'lxml')
        steps = soup.find('div', class_='next-steps')
        if not steps:
            return []
        return [step.get_text(strip=True) for step in steps.find_all('li')]


class Source(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200))
    repository = db.Column(db.String(100), nullable=False)  # Added repository field
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=False)
    fetch_date = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(pytz.UTC))


class BlockchainTerm(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(100), unique=True, nullable=False)
    explanation = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(pytz.UTC))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(pytz.UTC))