# MS6/main.py

import asyncio
from app.logging_config import setup_logging, logger # <-- This import now works

def main():
    """
    The main entry point for the Inference Executor (MS6) application.
    """
    setup_logging() # Configure the logger first
    worker_instance = RabbitMQWorker() # Renamed to avoid confusion with the module name
    
    try:
        logger.info("Starting Inference Executor Worker...")
        asyncio.run(worker_instance.run()) # Use the instance
    except KeyboardInterrupt:
        logger.info("Executor shutting down gracefully due to user request (CTRL+C).")
    except Exception as e:
        logger.critical(f"FATAL: Worker crashed during startup: {e}", exc_info=True)

# You need to import the worker class to use it
from app.messaging.worker import RabbitMQWorker

if __name__ == "__main__":
    main()