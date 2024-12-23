import logging
import socket
from app import app

if __name__ == "__main__":
    try:
        # Set debug level logging
        logging.basicConfig(level=logging.DEBUG)
        logger = logging.getLogger(__name__)

        # Find an available port starting from 5000
        port = 5000
        max_port = 5010  # Try up to port 5010

        while port <= max_port:
            try:
                # Test if port is available
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.bind(('0.0.0.0', port))
                sock.close()
                break
            except socket.error:
                port += 1

        if port > max_port:
            logger.error("No available ports found between 5000 and 5010")
            raise RuntimeError("No available ports")

        logger.info(f"Starting Flask server on port {port}...")
        app.run(host="0.0.0.0", port=port, debug=True)
    except Exception as e:
        logger.error(f"Failed to start Flask server: {str(e)}")
        raise