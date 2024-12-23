import logging
from app import app

if __name__ == "__main__":
    try:
        # Set debug level logging
        logging.basicConfig(level=logging.DEBUG)
        logger = logging.getLogger(__name__)
        logger.info("Starting Flask server on port 5000...")

        # Start server with proper host binding
        app.run(host="0.0.0.0", port=5000, debug=True)
    except Exception as e:
        logger.error(f"Failed to start Flask server: {str(e)}")
        raise