import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import WeeklyMetrics
import logging

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def add_weekly_metrics_table():
    """Add WeeklyMetrics table to store Dune Analytics data"""
    with app.app_context():
        try:
            # Create the table
            logger.info("Creating WeeklyMetrics table")
            db.create_all()
            logger.info("Successfully created WeeklyMetrics table")
            return True
        except Exception as e:
            logger.error(f"Error creating WeeklyMetrics table: {str(e)}")
            return False

if __name__ == '__main__':
    success = add_weekly_metrics_table()
    exit_code = 0 if success else 1
    sys.exit(exit_code)
