
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

def backup_database():
    """Backup the database based on environment"""
    try:
        with app.app_context():
            is_production = os.environ.get('REPL_ENVIRONMENT') == 'production'
            timestamp = datetime.now(pytz.UTC).strftime('%Y%m%d_%H%M%S')
            
            if is_production:
                # For PostgreSQL, use pg_dump
                database_url = os.environ.get("DATABASE_URL")
                if not database_url:
                    raise ValueError("DATABASE_URL not set in production")
                
                backup_file = f'backup_prod_{timestamp}.sql'
                backup_dir = 'instance/backups'
                os.makedirs(backup_dir, exist_ok=True)
                backup_path = os.path.join(backup_dir, backup_file)
                os.system(f'pg_dump {database_url} > {backup_path}')
                logger.info(f"Production database backed up to {backup_path}")
            else:
                # For SQLite, just copy the file
                src = "instance/development.db"
                backup_file = f'backup_dev_{timestamp}.db'
                if os.path.exists(src):
                    shutil.copy2(src, backup_file)
                    logger.info(f"Development database backed up to {backup_file}")
                else:
                    logger.warning("No development database found to backup")

    except Exception as e:
        logger.error(f"Error backing up database: {str(e)}")
        raise

if __name__ == '__main__':
    backup_database()
