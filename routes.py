from datetime import datetime, timedelta
from functools import wraps
from typing import Tuple, Union, List
import os
import glob
from scripts.backup_database import backup_database
from scripts.restore_database import restore_database

from flask import render_template, abort, flash, redirect, url_for, request, Response, jsonify, send_file
from flask_login import current_user, login_user, logout_user, login_required

from app import app, db
from models import Article, User, Source
import pytz
import logging
from services.new_article_generation_service import NewArticleGenerationService

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

        logger.info("Fetching articles for home page")

        # Get published articles ordered by publication date
        query = Article.query.filter_by(status='published').order_by(Article.publication_date.desc())
        total_count = Article.query.count()
        published_count = query.count()
        logger.info(f"Total articles in database: {total_count}")
        logger.info(f"Published articles in database: {published_count}")

        # Log the total number of articles before pagination
        total_articles = query.count()
        logger.info(f"Total published articles in database: {total_articles}")

        # Paginate the results
        paginated_articles = query.paginate(page=page, per_page=per_page, error_out=False)

        if paginated_articles and paginated_articles.items:
            logger.info(f"Found {len(paginated_articles.items)} articles on page {page}")
            # Get the first article as current week's article only on first page
            current_week_article = paginated_articles.items[0] if page == 1 else None

            # Create a new query excluding the current week article
            if current_week_article and page == 1:
                other_query = Article.query.filter_by(status='published')\
                    .filter(Article.id != current_week_article.id)\
                    .order_by(Article.publication_date.desc())
                other_articles = other_query.paginate(page=page, per_page=per_page, error_out=False)
            else:
                other_articles = paginated_articles

            if current_week_article:
                logger.info(f"Current week article: {current_week_article.title}")
            else:
                logger.warning("No current week article available")
        else:
            logger.warning("No articles found in pagination")
            current_week_article = None
            other_articles = None

        return render_template('index.html', 
                              current_week_article=current_week_article,
                              other_articles=other_articles)

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

def get_backup_files() -> List[str]:
    """Get list of available backup files"""
    try:
        # Create backup directories if they don't exist
        backup_dir = os.path.join(os.getcwd(), 'instance', 'backups')
        os.makedirs(backup_dir, exist_ok=True)

        # Create separate directories for dev and prod backups
        dev_backup_dir = os.path.join(backup_dir, 'dev')
        prod_backup_dir = os.path.join(backup_dir, 'prod')
        os.makedirs(dev_backup_dir, exist_ok=True)
        os.makedirs(prod_backup_dir, exist_ok=True)

        # Get environment and set appropriate directory
        is_production = os.environ.get('REPL_ENVIRONMENT') == 'production'
        current_dir = prod_backup_dir if is_production else dev_backup_dir

        # List backup files with full paths
        if is_production:
            backups = glob.glob(os.path.join(prod_backup_dir, 'backup_prod_*.sql'))
            logger.info(f"Found {len(backups)} production backups in {prod_backup_dir}")
        else:
            backups = glob.glob(os.path.join(dev_backup_dir, 'backup_dev_*.db'))
            logger.info(f"Found {len(backups)} development backups in {dev_backup_dir}")

        return sorted(backups, reverse=True)
    except Exception as e:
        logger.error(f"Error listing backup files: {str(e)}", exc_info=True)
        return []

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard() -> str:
    """Render the admin dashboard."""
    articles = Article.query.order_by(Article.publication_date.desc()).all()
    backups = get_backup_files()
    logger.info(f"Admin dashboard accessed by {current_user.email}")
    return render_template('admin/dashboard.html', articles=articles, backups=backups)

@app.route('/admin/backups')
@login_required
@admin_required
def backup_management():
    """Render backup management page"""
    try:
        backups = []
        backup_files = get_backup_files()

        for filename in backup_files:
            try:
                stat = os.stat(filename)
                created = datetime.fromtimestamp(stat.st_ctime, pytz.UTC)
                backups.append({
                    'filename': os.path.basename(filename),
                    'created': created.strftime('%Y-%m-%d %H:%M:%S UTC'),
                    'size': f"{stat.st_size / 1024 / 1024:.2f} MB"
                })
            except OSError as e:
                logger.error(f"Error accessing backup file {filename}: {str(e)}")
                continue

        is_production = os.environ.get('REPL_ENVIRONMENT') == 'production'
        env_type = 'production' if is_production else 'development'
        logger.info(f"Displaying {len(backups)} backups for {env_type}")

        return render_template('admin/backup_management.html', backups=backups)

    except Exception as e:
        logger.error(f"Error in backup management: {str(e)}", exc_info=True)
        flash('Error loading backups', 'error')
        return render_template('admin/backup_management.html', backups=[])

@app.route('/admin/backup/create', methods=['POST'])
@login_required
@admin_required
def create_backup():
    """Handle database backup creation"""
    try:
        # Get environment-specific backup directory
        backup_dir = os.path.join(os.getcwd(), 'instance', 'backups')
        is_production = os.environ.get('REPL_ENVIRONMENT') == 'production'
        env_dir = os.path.join(backup_dir, 'prod' if is_production else 'dev')

        # Ensure backup directory exists
        os.makedirs(env_dir, exist_ok=True)

        # Create backup
        backup_database()

        # Log success and verify backup creation
        backup_files = get_backup_files()
        if backup_files:
            latest_backup = os.path.basename(backup_files[0])
            logger.info(f"Created new backup: {latest_backup} in {env_dir}")
            flash('Database backup created successfully', 'success')
        else:
            logger.error("Backup file not found after creation")
            flash('Backup created but file not found', 'warning')

    except Exception as e:
        logger.error(f"Error creating backup: {str(e)}", exc_info=True)
        flash('Error creating backup', 'error')
    return redirect(url_for('backup_management'))

@app.route('/admin/backup/restore', methods=['POST'])
@login_required
@admin_required
def restore_backup():
    """Handle database restore"""
    backup_file = request.form.get('backup_file')
    if not backup_file:
        flash('No backup file selected', 'error')
        return redirect(url_for('backup_management'))

    try:
        # Get the full path from the environment-specific backup directory
        backup_dir = os.path.join('instance', 'backups')
        is_production = os.environ.get('REPL_ENVIRONMENT') == 'production'
        env_dir = os.path.join(backup_dir, 'prod' if is_production else 'dev')
        full_path = os.path.join(env_dir, backup_file)

        if not os.path.exists(full_path):
            flash('Backup file not found', 'error')
            return redirect(url_for('backup_management'))

        restore_database(full_path)
        flash('Database restored successfully', 'success')
        logger.info(f"Restored backup from {full_path}")
    except Exception as e:
        logger.error(f"Error restoring backup: {str(e)}", exc_info=True)
        flash('Error restoring backup', 'error')
    return redirect(url_for('backup_management'))

@app.route('/admin/backup/download/<filename>')
@login_required
@admin_required
def download_backup(filename):
    """Download a backup file"""
    try:
        # Get environment-specific backup directory
        backup_dir = os.path.join('instance', 'backups')
        is_production = os.environ.get('REPL_ENVIRONMENT') == 'production'
        env_dir = os.path.join(backup_dir, 'prod' if is_production else 'dev')
        file_path = os.path.join(env_dir, filename)

        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            flash('Backup file not found', 'error')
            return redirect(url_for('backup_management'))
    except Exception as e:
        logger.error(f"Error downloading backup {filename}: {str(e)}")
        flash('Error downloading backup', 'error')
        return redirect(url_for('backup_management'))

@app.route('/admin/backup/upload', methods=['POST'])
@login_required
@admin_required
def upload_backup():
    """Upload a backup file"""
    try:
        if 'backup_file' not in request.files:
            flash('No file uploaded', 'error')
            return redirect(url_for('backup_management'))
            
        file = request.files['backup_file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('backup_management'))

        # Get environment-specific backup directory
        backup_dir = os.path.join('instance', 'backups')
        is_production = os.environ.get('REPL_ENVIRONMENT') == 'production'
        env_dir = os.path.join(backup_dir, 'prod' if is_production else 'dev')
        os.makedirs(env_dir, exist_ok=True)

        timestamp = datetime.now(pytz.UTC).strftime('%Y%m%d_%H%M%S')
        prefix = 'backup_prod_' if is_production else 'backup_dev_'
        extension = '.sql' if is_production else '.db'
        new_filename = f"{prefix}{timestamp}{extension}"
        file_path = os.path.join(env_dir, new_filename)
        
        file.save(file_path)
        flash('Backup uploaded successfully', 'success')
        logger.info(f"Backup uploaded: {new_filename}")
        
    except Exception as e:
        logger.error(f"Error uploading backup: {str(e)}")
        flash('Error uploading backup', 'error')
    
    return redirect(url_for('backup_management'))

@app.route('/admin/backup/delete', methods=['POST'])
@login_required
@admin_required
def delete_backup():
    """Handle backup deletion"""
    backup_file = request.form.get('backup_file')
    if not backup_file:
        flash('No backup file selected', 'error')
        return redirect(url_for('backup_management'))

    try:
        # Get the full path from the environment-specific backup directory
        backup_dir = os.path.join('instance', 'backups')
        is_production = os.environ.get('REPL_ENVIRONMENT') == 'production'
        env_dir = os.path.join(backup_dir, 'prod' if is_production else 'dev')
        full_path = os.path.join(env_dir, backup_file)

        if not os.path.exists(full_path):
            flash('Backup file not found', 'error')
            return redirect(url_for('backup_management'))

        os.remove(full_path)
        flash('Backup deleted successfully', 'success')
        logger.info(f"Deleted backup {full_path}")
    except Exception as e:
        logger.error(f"Error deleting backup {backup_file}: {str(e)}", exc_info=True)
        flash('Error deleting backup', 'error')
    return redirect(url_for('backup_management'))

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
                author_id=current_user.id,
                status='published'  # Set status to published by default
            )
            db.session.add(article)
            db.session.commit()

            logger.info(f"New article created: {article.id} by {current_user.email} with status: {article.status}")
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
            custom_url = request.form.get('custom_url')

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
            article.custom_url = custom_url
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

@app.route('/article/<path:article_path>')
def article(article_path: str) -> Union[str, Tuple[str, int]]:
    """Display a single article."""
    try:
        # Try to find by custom URL first
        article = Article.query.filter_by(custom_url=article_path).first()

        # If not found, try to find by ID
        if not article and article_path.isdigit():
            article = Article.query.get(int(article_path))

        if not article:
            logger.warning(f"Article not found for path: {article_path}")
            abort(404)

        logger.info(f"Retrieved article: {article.id}")
        return render_template('article.html', article=article)
    except Exception as e:
        logger.error(f"Error retrieving article for path {article_path}: {str(e)}", exc_info=True)
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
        current_time=get_current_utc,
        timedelta=timedelta  # Add timedelta to template context
    )

# Add new route for technical terms API
@app.route('/api/technical-terms')
def get_technical_terms():
    """Return a dictionary of technical terms and their explanations."""
    terms = BlockchainTerm.query.all()
    return {term.term: term.explanation for term in terms}


@app.route('/admin/article/<int:article_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_article(article_id: int):
    """Handle deletion of an article."""
    try:
        article = Article.query.get_or_404(article_id)

        # Delete associated sources first
        Source.query.filter_by(article_id=article.id).delete()

        # Delete the article
        db.session.delete(article)
        db.session.commit()

        logger.info(f"Article {article_id} deleted by {current_user.email}")
        flash('Article deleted successfully', 'success')

    except Exception as e:
        logger.error(f"Error deleting article {article_id}: {str(e)}")
        db.session.rollback()
        flash('An error occurred while deleting the article.', 'error')

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/generate-article', methods=['POST'])
@login_required
@admin_required
def generate_single_article():
    """Handle generation of a single article."""
    try:
        generation_date_str = request.form.get('generation_date')
        if not generation_date_str:
            flash('Generation date is required.', 'error')
            return redirect(url_for('admin_dashboard'))

        try:
            generation_date = datetime.strptime(generation_date_str, '%Y-%m-%d')
            if generation_date.weekday() != 0:
                # Adjust to the Monday of the selected week
                generation_date = generation_date - timedelta(days=generation_date.weekday())
            generation_date = pytz.UTC.localize(generation_date)
        except ValueError as e:
            logger.error(f"Invalid date format: {str(e)}")
            flash('Invalid date format.', 'error')
            return redirect(url_for('admin_dashboard'))

        # Initialize new article generation service
        generation_service = NewArticleGenerationService()

        # Log environment information
        is_production = os.environ.get('REPL_ENVIRONMENT') == 'production'
        is_deployment = os.environ.get('REPLIT_DEPLOYMENT') == '1'
        has_db_url = bool(os.environ.get('DATABASE_URL'))

        logger.info(f"Article generation request - Environment: Production={is_production}, "
                   f"Deployment={is_deployment}, Database configured={has_db_url}")

        # Try to generate an article for the specified date
        article = generation_service.generate_article(generation_date)

        if article:
            flash('Article generation started. Check the status in the dashboard.', 'success')
            logger.info(f"Started generating article with ID: {article.id} for date {generation_date}")
        else:
            status = generation_service.get_generation_status()
            if status.get("is_generating"):
                flash('Another article is currently being generated. Please wait.', 'warning')
            else:
                error_details = []
                if not os.environ.get('DATABASE_URL'):
                    error_details.append("Database URL not configured")
                if status.get("error"):
                    error_details.append(status.get("error"))

                error_message = " | ".join(error_details) if error_details else "Unknown error occurred"
                flash(f'Failed to start article generation: {error_message}', 'error')
                logger.error(f"Article generation failed: {error_message}")

    except Exception as e:
        logger.error(f"Error starting article generation: {str(e)}", exc_info=True)
        flash('An error occurred while starting article generation.', 'error')

    return redirect(url_for('admin_dashboard'))

@app.route('/api/generation-status')
@login_required
@admin_required
def get_generation_status():
    """Get the current article generation status."""
    try:
        service = NewArticleGenerationService()
        status = service.get_generation_status()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Error getting generation status: {str(e)}")
        return jsonify({
            "is_generating": False,
            "status": "error",
            "error": str(e)
        }), 500