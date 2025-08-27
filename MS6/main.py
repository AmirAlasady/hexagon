import asyncio
from app.config import *
from app.logging_config import setup_logging
from app.messaging.worker import RabbitMQWorker
import logging

async def main():
    """Asynchronous entry point for the application."""
    setup_logging()
    logger = logging.getLogger("MS6-Executor")
    worker = RabbitMQWorker()
    try:
        logger.info("Starting Inference Executor Worker...")
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Executor shutting down gracefully due to user request (CTRL+C).")
    except Exception as e:
        logger.critical(f"FATAL: Worker crashed during startup: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())