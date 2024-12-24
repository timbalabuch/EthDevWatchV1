from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db

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
    publication_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    sources = db.relationship('Source', backref='article', lazy=True)

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
        self.published_date = datetime.utcnow()
        db.session.commit()

    def schedule(self, publish_date):
        self.status = 'scheduled'
        self.scheduled_publish_date = publish_date
        db.session.commit()

class Source(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200))
    repository = db.Column(db.String(100), nullable=False)  # Added repository field
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=False)
    fetch_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)