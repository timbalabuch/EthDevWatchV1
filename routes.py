from datetime import datetime, timedelta
from functools import wraps
from typing import Tuple, Union

from flask import render_template, abort, flash, redirect, url_for, request, Response
from flask_login import current_user, login_user, logout_user, login_required

from app import app, db
from models import Article, User, Source
import pytz
import logging

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def admin_required(f):
    """Decorator to restrict access to admin users only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            logger.warning(f"Unauthorized admin access attempt by user: {current_user.id if current_user.is_authenticated else 'anonymous'}")
            flash('You need to be an admin to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_utc() -> datetime:
    """Get current UTC time with timezone information."""
    return datetime.now(pytz.UTC)

def get_last_completed_week() -> Tuple[datetime, datetime]:
    """Get the date range for the last completed week."""
    current_date = get_current_utc()
    days_since_sunday = current_date.weekday() + 1
    last_sunday = current_date - timedelta(days=days_since_sunday)
    last_sunday = last_sunday.replace(hour=23, minute=59, second=59, microsecond=999999)
    last_monday = last_sunday - timedelta(days=6)
    last_monday = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)
    return last_monday, last_sunday

@app.route('/')
def index() -> str:
    """Render the home page with a list of articles."""
    try:
        # Get page number from request
        page = request.args.get('page', 1, type=int)
        per_page = 6

        # Get all articles with pagination, ordered by publication date
        articles = Article.query.order_by(Article.publication_date.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        logger.info(f"Found {articles.total} total articles")

        return render_template('index.html', 
                            current_week_article=articles.items[0] if articles.items else None,
                            other_articles=articles)

    except Exception as e:
        logger.error(f"Error retrieving articles: {str(e)}", exc_info=True)
        return render_template('index.html', 
                            current_week_article=None,
                            other_articles=None)

@app.route('/login', methods=['GET', 'POST'])
def login() -> Union[str, Response]:
    """Handle user login."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if not email or not password:
            flash('Email and password are required.', 'error')
            return render_template('login.html')

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            logger.info(f"User {user.email} logged in successfully")
            return redirect(url_for('index'))

        logger.warning(f"Failed login attempt for email: {email}")
        flash('Invalid email or password', 'error')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout() -> Response:
    """Handle user logout."""
    if current_user.is_authenticated:
        logger.info(f"User {current_user.email} logged out")
    logout_user()
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard() -> str:
    """Render the admin dashboard."""
    articles = Article.query.order_by(Article.publication_date.desc()).all()
    logger.info(f"Admin dashboard accessed by {current_user.email}")
    return render_template('admin/dashboard.html', articles=articles)

@app.route('/admin/article/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_article() -> Union[str, Response]:
    """Handle creation of new articles."""
    if request.method == 'POST':
        try:
            # Validate required fields
            title = request.form.get('title')
            content = request.form.get('content')
            pub_date_str = request.form.get('publication_date')

            if not all([title, content, pub_date_str]):
                flash('All fields are required.', 'error')
                return render_template('admin/article_form.html')

            pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d')
            pub_date = pytz.UTC.localize(pub_date)

            if pub_date > get_current_utc():
                flash('Publication date cannot be in the future', 'error')
                return render_template('admin/article_form.html')

            article = Article(
                title=title,
                content=content,
                publication_date=pub_date,
                author_id=current_user.id
            )
            db.session.add(article)
            db.session.commit()

            logger.info(f"New article created: {article.id} by {current_user.email}")
            flash('Article created successfully', 'success')
            return redirect(url_for('admin_dashboard'))

        except ValueError as e:
            logger.error(f"Invalid date format in new article creation: {str(e)}")
            flash('Invalid date format. Please use YYYY-MM-DD format.', 'error')
            return render_template('admin/article_form.html')
        except Exception as e:
            logger.error(f"Error creating new article: {str(e)}")
            db.session.rollback()
            flash('An error occurred while creating the article.', 'error')
            return render_template('admin/article_form.html')

    return render_template('admin/article_form.html')

@app.route('/admin/article/<int:article_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_article(article_id: int) -> Union[str, Response]:
    """Handle editing of existing articles."""
    article = Article.query.get_or_404(article_id)

    if request.method == 'POST':
        try:
            # Validate required fields
            title = request.form.get('title')
            content = request.form.get('content')
            pub_date_str = request.form.get('publication_date')

            if not all([title, content, pub_date_str]):
                flash('All fields are required.', 'error')
                return render_template('admin/article_form.html', article=article)

            pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d')
            pub_date = pytz.UTC.localize(pub_date)

            if pub_date > get_current_utc():
                flash('Publication date cannot be in the future', 'error')
                return render_template('admin/article_form.html', article=article)

            article.title = title
            article.content = content
            article.publication_date = pub_date
            db.session.commit()

            logger.info(f"Article {article_id} updated by {current_user.email}")
            flash('Article updated successfully', 'success')
            return redirect(url_for('admin_dashboard'))

        except ValueError as e:
            logger.error(f"Invalid date format in article edit: {str(e)}")
            flash('Invalid date format. Please use YYYY-MM-DD format.', 'error')
            return render_template('admin/article_form.html', article=article)
        except Exception as e:
            logger.error(f"Error updating article {article_id}: {str(e)}")
            db.session.rollback()
            flash('An error occurred while updating the article.', 'error')
            return render_template('admin/article_form.html', article=article)

    return render_template('admin/article_form.html', article=article)

@app.route('/article/<int:article_id>')
def article(article_id: int) -> Union[str, Tuple[str, int]]:
    """Display a single article."""
    try:
        logger.info(f"Attempting to retrieve article with ID: {article_id}")
        article = Article.query.get_or_404(article_id)
        
        logger.info(f"Article found: {article.title}")
        return render_template('article.html', article=article)
    except Exception as e:
        logger.error(f"Error retrieving article {article_id}: {str(e)}", exc_info=True)
        return render_template('404.html'), 404

@app.errorhandler(404)
def page_not_found(e) -> Tuple[str, int]:
    """Handle 404 errors."""
    logger.warning(f"404 error: {request.url}")
    return render_template('404.html'), 404

@app.context_processor
def utility_processor() -> dict:
    """Add utility functions to template context."""
    def format_date(date: datetime) -> str:
        """Format a date object for display."""
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

# Add new route for technical terms API
@app.route('/api/technical-terms')
def get_technical_terms():
    """Return a dictionary of technical terms and their explanations."""
    terms = BlockchainTerm.query.all()
    return {term.term: term.explanation for term in terms}