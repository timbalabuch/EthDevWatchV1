import logging
from app import app

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        logger.info("Starting Flask server...")
        port = int(os.environ.get('PORT', 3000))
        app.run(host='0.0.0.0', port=port)
    except Exception as e:
        logger.error(f"Failed to start Flask server: {str(e)}")
        raise