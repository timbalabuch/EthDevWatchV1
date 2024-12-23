import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from services.github_service import GitHubService
from services.content_service import ContentService

logger = logging.getLogger(__name__)

def generate_weekly_update():
    """Task to generate weekly update"""
    try:
        github_service = GitHubService()
        content_service = ContentService()
        
        # Fetch content from GitHub
        github_content = github_service.fetch_recent_content()
        
        if github_content:
            # Generate and store summary
            article = content_service.generate_weekly_summary(github_content)
            logger.info(f"Generated weekly update: {article.title}")
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
    logger.info("Scheduler initialized")
