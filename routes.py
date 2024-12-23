from datetime import datetime, timedelta
from flask import render_template, abort
from app import app
from models import Article

@app.route('/')
def index():
    articles = Article.query.order_by(Article.publication_date.desc()).all()
    return render_template('index.html', articles=articles)

@app.route('/article/<int:article_id>')
def article(article_id):
    article = Article.query.get_or_404(article_id)
    return render_template('article.html', article=article)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.context_processor
def utility_processor():
    def now(timezone, format):
        from datetime import datetime
        from pytz import timezone as tz
        return datetime.now(tz(timezone)).strftime(format)

    # Add timedelta to template context
    return dict(now=now, timedelta=timedelta)