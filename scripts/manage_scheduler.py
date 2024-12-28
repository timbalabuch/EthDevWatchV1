import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from services.scheduler import init_scheduler
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def enable_scheduler():
    """Enable the article generation scheduler."""
    try:
        with app.app_context():
            scheduler = init_scheduler(auto_start=True)
            if scheduler.running:
                logger.info("Article generation scheduler is now running")
                logger.info("Next article will be generated on Monday at 9:00 UTC")
                return True
            else:
                logger.error("Failed to start the scheduler")
                return False
    except Exception as e:
        logger.error(f"Error enabling scheduler: {str(e)}")
        return False

def disable_scheduler():
    """Disable the article generation scheduler."""
    try:
        with app.app_context():
            scheduler = init_scheduler(auto_start=False)
            if not scheduler.running:
                logger.info("Article generation scheduler is now disabled")
                return True
            else:
                logger.error("Failed to disable the scheduler")
                return False
    except Exception as e:
        logger.error(f"Error disabling scheduler: {str(e)}")
        return False

if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in ['enable', 'disable']:
        print("Usage: python manage_scheduler.py [enable|disable]")
        sys.exit(1)

    command = sys.argv[1]
    success = enable_scheduler() if command == 'enable' else disable_scheduler()
    sys.exit(0 if success else 1)
