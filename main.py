import logging
from app import app

if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, debug=True)
    except Exception as e:
        logging.error(f"Failed to start Flask server: {str(e)}")
        raise