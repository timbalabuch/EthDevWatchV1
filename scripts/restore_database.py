
import sys
import os
import shutil
from datetime import datetime
import pytz
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app, db

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def restore_database(backup_file):
    """Restore the database from a backup file"""
    try:
        with app.app_context():
            is_production = os.environ.get('REPL_ENVIRONMENT') == 'production'
            
            if not os.path.exists(backup_file):
                raise ValueError(f"Backup file not found: {backup_file}")
            
            if is_production:
                # For PostgreSQL, use psql
                database_url = os.environ.get("DATABASE_URL")
                if not database_url:
                    raise ValueError("DATABASE_URL not set in production")
                
                os.system(f'psql {database_url} < {backup_file}')
                logger.info(f"Production database restored from {backup_file}")
            else:
                # For SQLite, replace the file
                dest = "instance/development.db"
                shutil.copy2(backup_file, dest)
                logger.info(f"Development database restored from {backup_file}")

    except Exception as e:
        logger.error(f"Error restoring database: {str(e)}")
        raise

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python restore_database.py <backup_file>")
        sys.exit(1)
    
    backup_file = sys.argv[1]
    restore_database(backup_file)
