from datetime import datetime, timedelta
from flask import render_template, abort, flash, redirect, url_for, request
from flask_login import current_user, login_user, logout_user, login_required
from app import app, db
from models import Article, User, Source
from functools import wraps

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You need to be an admin to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    # Only show articles from past weeks and up to current date
    current_date = datetime.utcnow()
    articles = Article.query.filter(
        Article.publication_date <= current_date
    ).order_by(Article.publication_date.desc()).all()
    return render_template('index.html', articles=articles)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid email or password', 'error')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    articles = Article.query.order_by(Article.publication_date.desc()).all()
    return render_template('admin/dashboard.html', articles=articles)

@app.route('/admin/article/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_article():
    if request.method == 'POST':
        article = Article(
            title=request.form['title'],
            content=request.form['content'],
            publication_date=datetime.strptime(request.form['publication_date'], '%Y-%m-%d'),
            author_id=current_user.id
        )
        db.session.add(article)
        db.session.commit()
        flash('Article created successfully', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/article_form.html')

@app.route('/admin/article/<int:article_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_article(article_id):
    article = Article.query.get_or_404(article_id)
    if request.method == 'POST':
        article.title = request.form['title']
        article.content = request.form['content']
        article.publication_date = datetime.strptime(request.form['publication_date'], '%Y-%m-%d')
        db.session.commit()
        flash('Article updated successfully', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/article_form.html', article=article)

@app.route('/article/<int:article_id>')
def article(article_id):
    article = Article.query.get_or_404(article_id)
    # Don't show future articles
    current_date = datetime.utcnow()
    if article.publication_date > current_date:
        abort(404)
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
    return dict(now=now, timedelta=timedelta)