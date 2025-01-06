import logging
import os
import socket
from app import app

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def find_available_port(start_port=5000, max_port=5100):
    """Find an available port starting from start_port up to max_port."""
    for port in range(start_port, max_port):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('0.0.0.0', port))
                s.close()  # Important: close the socket after checking
                logger.info(f"Found available port: {port}")
                return port
        except socket.error:
            logger.debug(f"Port {port} is in use, trying next port")
            continue
    raise RuntimeError(f"No available ports found between {start_port} and {max_port}")

if __name__ == "__main__":
    try:
        logger.info("Starting Flask server...")
        # Try port 5000 first, if not available, find another port
        try:
            port = 5000
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('0.0.0.0', port))
                s.close()
        except socket.error:
            logger.warning("Port 5000 is in use, finding another port...")
            port = find_available_port(start_port=5001, max_port=5100)

        logger.info(f"Server will start on port {port}")
        app.run(host='0.0.0.0', port=port, debug=True)
    except Exception as e:
        logger.error(f"Failed to start Flask server: {str(e)}")
        raise