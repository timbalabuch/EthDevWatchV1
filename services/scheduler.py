import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
from services.github_service import GitHubService
from services.content_service import ContentService
from app import db, app
from models import Article

logger = logging.getLogger(__name__)

def get_previous_week_dates():
    """Get the start and end dates for the previous week (Monday to Sunday)"""
    current_date = datetime.utcnow()
    current_date = current_date.replace(hour=0, minute=0, second=0, microsecond=0)

    # Calculate previous week's Monday and Sunday
    days_since_monday = current_date.weekday()
    previous_monday = current_date - timedelta(days=days_since_monday + 7)
    previous_sunday = previous_monday + timedelta(days=6)

    return previous_monday, previous_sunday

def generate_weekly_article():
    """Generate article for the previous week's content"""
    try:
        with app.app_context():
            # Get previous week's date range
            start_date, end_date = get_previous_week_dates()

            logger.info(f"Generating article for week of {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

            # Check if article already exists for this week
            existing = Article.query.filter(
                Article.publication_date >= start_date,
                Article.publication_date <= end_date
            ).first()

            if existing:
                logger.info(f"Article already exists for week of {start_date.strftime('%Y-%m-%d')}: {existing.title}")
                return

            # Initialize services
            github_service = GitHubService()
            content_service = ContentService()

            # Fetch content specifically for the previous week
            github_content = github_service.fetch_recent_content(
                start_date=start_date,
                end_date=end_date
            )

            if github_content:
                # Generate and publish article immediately
                article = content_service.generate_weekly_summary(
                    github_content,
                    publication_date=start_date
                )

                if article:
                    article.status = 'published'
                    article.published_date = datetime.utcnow()
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

    # Generate articles every Monday at 9:00 UTC for the previous week
    scheduler.add_job(
        generate_weekly_article,
        trigger=CronTrigger(day_of_week='mon', hour=9, minute=0),
        id='generate_weekly_article',
        name='Generate weekly Ethereum update',
        replace_existing=True
    )

    scheduler.start()
    logger.info("Scheduler initialized with article generation task")