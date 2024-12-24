from datetime import datetime, timedelta
from flask import render_template, abort, flash, redirect, url_for, request
from flask_login import current_user, login_user, logout_user, login_required
from app import app, db
from models import Article, User, Source
from functools import wraps
import pytz
import logging

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

def get_last_completed_week():
    """Get the date range for the last completed week"""
    current_date = get_current_utc()

    # Calculate the last completed Sunday
    days_since_sunday = current_date.weekday() + 1  # +1 because we want the previous Sunday
    last_sunday = current_date - timedelta(days=days_since_sunday)
    last_sunday = last_sunday.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Get the Monday of that week
    last_monday = last_sunday - timedelta(days=6)
    last_monday = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)

    return last_monday, last_sunday

@app.route('/')
def index():
    last_monday, last_sunday = get_last_completed_week()
    logger.info(f"Filtering articles up to last completed week: {last_sunday.strftime('%Y-%m-%d')}")

    articles = Article.query.filter(
        Article.publication_date <= last_sunday
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
    last_monday, last_sunday = get_last_completed_week()

    # Don't show articles from incomplete weeks
    article_date = article.publication_date.replace(tzinfo=pytz.UTC) if article.publication_date.tzinfo is None else article.publication_date
    if article_date > last_sunday:
        logger.warning(f"Attempted to access future article {article_id} with date {article_date}")
        abort(404)

    # Add detailed logging for metrics
    if article.metrics:
        logger.info(f"Article {article_id} has metrics data")
        logger.debug(f"Active addresses: {article.metrics.active_addresses}")
        logger.debug(f"Contract deployments: {article.metrics.contracts_deployed}")
        logger.debug(f"ETH burned: {article.metrics.eth_burned}")
        logger.debug(f"Metrics period: {article.metrics.start_date} to {article.metrics.end_date}")
    else:
        logger.warning(f"No metrics found for article {article_id}")

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

        # Ensure date is timezone-aware
        if date.tzinfo is None:
            date = pytz.UTC.localize(date)

        # Get the Monday of the week
        monday = date.replace(hour=0, minute=0, second=0, microsecond=0)
        monday = monday - timedelta(days=monday.weekday())

        # Get the Sunday of the week
        sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

        logger.debug(f"Formatting date - Original: {date}, Monday: {monday}, Sunday: {sunday}")

        # Format as "Week of Month Day - Month Day, Year"
        if monday.month == sunday.month:
            return f"Week of {monday.strftime('%B %d')} - {sunday.strftime('%d, %Y')}"
        elif monday.year == sunday.year:
            return f"Week of {monday.strftime('%B %d')} - {sunday.strftime('%B %d, %Y')}"
        else:
            return f"Week of {monday.strftime('%B %d, %Y')} - {sunday.strftime('%B %d, %Y')}"

    return dict(
        format_date=format_date,
        current_time=get_current_utc
    )