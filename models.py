from datetime import datetime
from app import db

class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    publication_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    image_url = db.Column(db.String(500))  # New field for storing the image URL
    sources = db.relationship('Source', backref='article', lazy=True)

class Source(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # github, ethereum_pm, etc.
    title = db.Column(db.String(200))
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=False)
    fetch_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)