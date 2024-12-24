import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
from services.github_service import GitHubService
from services.content_service import ContentService
from app import db
from models import Article

logger = logging.getLogger(__name__)

def get_monday_of_week(date):
    """Get the Monday of the week for a given date"""
    return date - timedelta(days=date.weekday())

def get_sunday_of_week(date):
    """Get the Sunday of the week for a given date"""
    monday = get_monday_of_week(date)
    return monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

def generate_weekly_update():
    """Task to generate weekly update"""
    try:
        current_date = datetime.utcnow()
        monday = get_monday_of_week(current_date)
        sunday = get_sunday_of_week(current_date)

        # Check if article already exists for this week
        existing = Article.query.filter(
            Article.publication_date >= monday,
            Article.publication_date <= sunday
        ).first()

        if existing:
            logger.info(f"Article already exists for week of {monday.strftime('%Y-%m-%d')}: {existing.title}")
            return

        logger.info(f"Generating article for week of {monday.strftime('%Y-%m-%d')}")

        # Initialize services
        github_service = GitHubService()
        content_service = ContentService()

        # Fetch content from GitHub
        github_content = github_service.fetch_recent_content()

        if github_content:
            # Generate and store summary
            article = content_service.generate_weekly_summary(github_content, monday)
            if article:
                logger.info(f"Generated weekly update: {article.title}")
            else:
                logger.error("Failed to generate article")
        else:
            logger.warning("No content fetched from GitHub")

    except Exception as e:
        logger.error(f"Error in weekly update task: {str(e)}")

def init_scheduler():
    """Initialize the scheduler with weekly tasks"""
    scheduler = BackgroundScheduler()

    # Schedule weekly update for Monday at 00:00 UTC
    scheduler.add_job(
        generate_weekly_update,
        trigger=CronTrigger(day_of_week='mon', hour=0, minute=0),
        id='weekly_update',
        name='Generate weekly Ethereum update',
        replace_existing=True
    )

    scheduler.start()
    logger.info("Scheduler initialized with weekly article generation task")