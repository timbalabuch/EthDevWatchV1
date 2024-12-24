import logging
import socket
from app import app

if __name__ == "__main__":
    try:
        # Set debug level logging
        logging.basicConfig(level=logging.DEBUG)
        logger = logging.getLogger(__name__)

        # Always use port 5001 since 5000 is commonly used
        port = 5001

        logger.info(f"Starting Flask server on port {port}...")
        app.run(host="0.0.0.0", port=port, debug=True)
    except Exception as e:
        logger.error(f"Failed to start Flask server: {str(e)}")
        raise