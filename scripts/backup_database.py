
import sys
import os
import shutil
from datetime import datetime
import pytz
import logging
from replit.object_storage import Client

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app, db

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
                database_url = os.environ.get("DATABASE_URL")
                if not database_url:
                    raise ValueError("DATABASE_URL not set in production")
                
                backup_file = f'backup_prod_{timestamp}.sql'
                temp_path = f'/tmp/{backup_file}'
                
                # Create backup using pg_dump
                os.system(f'pg_dump {database_url} > {temp_path}')
                
                # Store in Object Storage
                with open(temp_path, 'rb') as f:
                    client = Client()
                    client.upload_file(temp_path, backup_file)
                
                # Cleanup temp file
                os.remove(temp_path)
                logger.info(f"Production database backed up to Object Storage: {backup_file}")
            else:
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
