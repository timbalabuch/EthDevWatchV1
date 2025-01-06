import logging
import os
from app import app

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        logger.info("Starting Flask server...")
        app.run(host='0.0.0.0', port=5000, debug=True)
    except OSError as e:
        if "Address already in use" in str(e):
            logger.error("Port 5000 is already in use. Please ensure no other application is using this port.")
        else:
            logger.error(f"Failed to start Flask server: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Failed to start Flask server: {str(e)}")
        raise