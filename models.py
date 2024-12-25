import logging
import re
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
import pytz
from bs4 import BeautifulSoup

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
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
    magicians_discussions = db.Column(db.Text)  # Separate field for Ethereum Magicians discussions
    ethresearch_discussions = db.Column(db.Text)  # Separate field for Ethereum Research discussions

    # Publishing workflow columns
    status = db.Column(db.String(20), nullable=False, default='draft')
    scheduled_publish_date = db.Column(db.DateTime)
    published_date = db.Column(db.DateTime)

    @property
    def brief_summary(self):
        """Extract brief summary from content."""
        if not self.content:
            return None
        try:
            soup = BeautifulSoup(self.content, 'lxml')
            overview = soup.find('div', class_='overview-section')
            if overview:
                overview_content = overview.find('div', class_='overview-content')
                if overview_content:
                    text = overview_content.get_text(strip=True)
                    return text[:350] + ('...' if len(text) > 350 else '')
            return None
        except Exception as e:
            logger.error(f"Error extracting brief summary: {e}")
            return None

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

class Source(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200))
    repository = db.Column(db.String(100), nullable=False)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=False)
    fetch_date = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(pytz.UTC))

class BlockchainTerm(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(100), unique=True, nullable=False)
    explanation = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(pytz.UTC))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(pytz.UTC))