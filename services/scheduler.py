import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import pytz
from services.github_service import GitHubService
from services.content_service import ContentService
from app import db, app
from models import Article

logger = logging.getLogger(__name__)

def get_previous_week_dates():
    """Get the start and end dates for the previous week (Monday to Sunday)"""
    current_date = datetime.now(pytz.UTC)
    current_date = current_date.replace(hour=0, minute=0, second=0, microsecond=0)

    # Calculate previous week's Monday
    days_since_monday = current_date.weekday()
    previous_monday = current_date - timedelta(days=days_since_monday + 7)
    previous_monday = previous_monday.replace(hour=0, minute=0, second=0, microsecond=0)

    # Calculate previous week's Sunday
    previous_sunday = previous_monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

    return previous_monday, previous_sunday

def generate_weekly_article():
    """Generate article for the previous week's content"""
    try:
        with app.app_context():
            # Get previous week's date range
            start_date, end_date = get_previous_week_dates()

            # Only generate if it's Monday
            current_date = datetime.now(pytz.UTC)
            if current_date.weekday() != 0:
                logger.info("Skipping article generation - not Monday")
                return

            logger.info(f"Generating article for week of {start_date.strftime('%Y-%m-%d')}")

            # Check if article already exists for this week
            existing = Article.query.filter(
                Article.publication_date >= start_date,
                Article.publication_date <= end_date
            ).first()

            if existing:
                logger.info(f"Article already exists for week: {existing.title}")
                if existing.status == 'published':
                    logger.info("Article is already published, skipping generation")
                    return
                elif existing.status == 'generating':
                    logger.info("Article is currently being generated, skipping")
                    return
                else:
                    logger.info(f"Article exists but has status: {existing.status}")
                    return

            # Initialize services
            github_service = GitHubService()
            content_service = ContentService()

            # Fetch content for the previous week only
            github_content = github_service.fetch_recent_content(
                start_date=start_date,
                end_date=end_date
            )

            if github_content:
                # Generate article with explicit Monday date
                article = content_service.generate_weekly_summary(
                    github_content,
                    publication_date=start_date
                )

                if article:
                    article.status = 'published'
                    article.published_date = current_date
                    db.session.commit()
                    logger.info(f"Generated and published article: {article.title}")
                else:
                    logger.error("Failed to generate article")
            else:
                logger.warning("No content found for the previous week")

    except Exception as e:
        logger.error(f"Error in weekly article generation task: {str(e)}")

def init_scheduler():
    """Initialize the scheduler with weekly article generation task"""
    scheduler = BackgroundScheduler()

    # Schedule article generation only on Mondays at 9:00 UTC
    scheduler.add_job(
        generate_weekly_article,
        trigger=CronTrigger(day_of_week='mon', hour=9, minute=0),
        id='generate_weekly_article',
        name='Generate weekly Ethereum update',
        replace_existing=True,
        misfire_grace_time=3600  # Allow 1 hour grace time for misfires
    )

    scheduler.start()
    logger.info("Scheduler initialized with article generation task")