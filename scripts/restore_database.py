
import sys
import os
import shutil
import logging
from replit.object_storage import Client

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def restore_database(backup_file):
    """Restore the database from a backup file"""
    try:
        with app.app_context():
            is_production = os.environ.get('REPL_ENVIRONMENT') == 'production'
            
            if is_production:
                database_url = os.environ.get("DATABASE_URL")
                if not database_url:
                    raise ValueError("DATABASE_URL not set in production")
                
                # Get from Object Storage
                client = Client()
                temp_path = f'/tmp/{backup_file}'
                client.download_file(backup_file, temp_path)
                
                # Restore from temp file
                os.system(f'psql {database_url} < {temp_path}')
                
                # Cleanup
                os.remove(temp_path)
                logger.info(f"Production database restored from Object Storage: {backup_file}")
            else:
                dest = "instance/development.db"
                if os.path.exists(backup_file):
                    shutil.copy2(backup_file, dest)
                    logger.info(f"Development database restored from {backup_file}")
                else:
                    raise ValueError(f"Backup file not found: {backup_file}")

    except Exception as e:
        logger.error(f"Error restoring database: {str(e)}")
        raise

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python restore_database.py <backup_file>")
        sys.exit(1)
    
    backup_file = sys.argv[1]
    restore_database(backup_file)
