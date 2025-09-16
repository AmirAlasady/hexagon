# MS10/messaging/rabbitmq_client.py

import pika
import json
import threading
import time
import logging
from django.conf import settings

# Use a specific logger for the client itself
logger = logging.getLogger(__name__)

class RabbitMQClient:
    """
    A robust, thread-safe RabbitMQ client that manages connections on a per-thread
    basis, uses a fresh channel per operation, and includes an automatic retry
    mechanism for publishing messages to handle transient network failures.
    """
    _thread_local = threading.local()

    def __init__(self, max_retries=3, retry_delay=2):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _get_connection(self):
        """Gets or creates a dedicated connection for the current thread."""
        if not hasattr(self._thread_local, 'connection') or self._thread_local.connection.is_closed:
            logger.info(f"Thread {threading.get_ident()}: No active RabbitMQ connection. Creating new one...")
            try:
                params = pika.URLParameters(settings.RABBITMQ_URL)
                self._thread_local.connection = pika.BlockingConnection(params)
                logger.info(f"Thread {threading.get_ident()}: Connection successful.")
            except pika.exceptions.AMQPConnectionError as e:
                logger.critical(f"Thread {threading.get_ident()} failed to connect to RabbitMQ: {e}", exc_info=True)
                raise
        return self._thread_local.connection

    def _invalidate_connection(self):
        """Forcefully closes and removes the connection for the current thread."""
        if hasattr(self._thread_local, 'connection') and self._thread_local.connection.is_open:
            self._thread_local.connection.close()
        if hasattr(self._thread_local, 'connection'):
            del self._thread_local.connection
        logger.warning(f"Thread {threading.get_ident()}: Invalidated RabbitMQ connection.")

    def publish(self, exchange_name, routing_key, body, exchange_type='topic'):
        """Publishes a message with a built-in retry mechanism."""
        attempt = 0
        while attempt < self.max_retries:
            try:
                connection = self._get_connection()
                with connection.channel() as channel:
                    logger.debug(f"Declaring exchange '{exchange_name}' of type '{exchange_type}'.")
                    channel.exchange_declare(
                        exchange=exchange_name,
                        exchange_type=exchange_type,
                        durable=True
                    )
                    
                    message_body = json.dumps(body, default=str)
                    channel.basic_publish(
                        exchange=exchange_name,
                        routing_key=routing_key,
                        body=message_body,
                        properties=pika.BasicProperties(
                            content_type='application/json',
                            delivery_mode=pika.DeliveryMode.Persistent,
                        )
                    )
                    logger.info(f"Successfully published to exchange '{exchange_name}' with key '{routing_key}' on attempt {attempt + 1}.")
                    return

            except (pika.exceptions.AMQPError, OSError) as e:
                logger.warning(f"Publish attempt {attempt + 1} to exchange '{exchange_name}' failed: {e}. Invalidating connection and retrying...", exc_info=True)
                self._invalidate_connection()
                attempt += 1
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    logger.critical(f"Failed to publish message to '{exchange_name}' after {self.max_retries} attempts. Giving up.")
                    raise

# Create a single, globally accessible instance.
rabbitmq_client = RabbitMQClient()