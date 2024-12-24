from datetime import datetime, timedelta
from flask import render_template, abort, flash, redirect, url_for, request
from flask_login import current_user, login_user, logout_user, login_required
from app import app, db
from models import Article, User, Source
from functools import wraps
import pytz

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You need to be an admin to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_utc():
    """Get current UTC time with timezone information"""
    return datetime.now(pytz.UTC)

@app.route('/')
def index():
    current_date = get_current_utc()
    articles = Article.query.filter(
        Article.publication_date <= current_date
    ).order_by(Article.publication_date.desc()).all()

    # Calculate end dates for each article
    for article in articles:
        pub_date = article.publication_date.replace(tzinfo=pytz.UTC) if article.publication_date.tzinfo is None else article.publication_date
        article.end_date = min(
            pub_date + timedelta(days=6),
            current_date
        )

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
        try:
            pub_date = datetime.strptime(request.form['publication_date'], '%Y-%m-%d')
            pub_date = pytz.UTC.localize(pub_date)

            if pub_date > get_current_utc():
                flash('Publication date cannot be in the future', 'error')
                return render_template('admin/article_form.html')

            article = Article(
                title=request.form['title'],
                content=request.form['content'],
                publication_date=pub_date,
                author_id=current_user.id
            )
            db.session.add(article)
            db.session.commit()
            flash('Article created successfully', 'success')
            return redirect(url_for('admin_dashboard'))
        except ValueError as e:
            flash('Invalid date format. Please use YYYY-MM-DD format.', 'error')
            return render_template('admin/article_form.html')
    return render_template('admin/article_form.html')

@app.route('/admin/article/<int:article_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_article(article_id):
    article = Article.query.get_or_404(article_id)
    if request.method == 'POST':
        try:
            pub_date = datetime.strptime(request.form['publication_date'], '%Y-%m-%d')
            pub_date = pytz.UTC.localize(pub_date)

            if pub_date > get_current_utc():
                flash('Publication date cannot be in the future', 'error')
                return render_template('admin/article_form.html', article=article)

            article.title = request.form['title']
            article.content = request.form['content']
            article.publication_date = pub_date
            db.session.commit()
            flash('Article updated successfully', 'success')
            return redirect(url_for('admin_dashboard'))
        except ValueError as e:
            flash('Invalid date format. Please use YYYY-MM-DD format.', 'error')
            return render_template('admin/article_form.html', article=article)
    return render_template('admin/article_form.html', article=article)

@app.route('/article/<int:article_id>')
def article(article_id):
    article = Article.query.get_or_404(article_id)
    current_date = get_current_utc()

    # Don't show future articles
    article_date = article.publication_date.replace(tzinfo=pytz.UTC) if article.publication_date.tzinfo is None else article.publication_date
    if article_date > current_date:
        abort(404)

    # Calculate end date for the article
    article.end_date = min(
        article_date + timedelta(days=6),
        current_date
    )

    return render_template('article.html', article=article)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.context_processor
def utility_processor():
    """Add utility functions to template context"""
    def format_date(date):
        """Format a date object for display"""
        if not date:
            return ''
        if not date.tzinfo:
            date = date.replace(tzinfo=pytz.UTC)
        return date.strftime('%B %d, %Y')

    return dict(
        format_date=format_date,
        current_time=get_current_utc
    )