# MS6/app/messaging/rabbitmq_client.py

import pika
import json
import threading
import time
from app import config
from app.logging_config import logger

class ThreadSafeRabbitMQClient:
    """
    A robust, thread-safe RabbitMQ client that manages connections on a per-thread
    basis. This is essential because the executor will process each job in a new thread,
    and each thread needs its own connection to RabbitMQ to publish results.
    """
    _thread_local = threading.local()

    def __init__(self, max_retries=3, retry_delay=2):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _get_connection(self):
        """Gets or creates a dedicated connection for the current thread."""
        if not hasattr(self._thread_local, 'connection') or self._thread_local.connection.is_closed:
            logger.info(f"Thread {threading.get_ident()}: No active publisher connection. Creating new one...")
            params = pika.URLParameters(config.RABBITMQ_URL)
            self._thread_local.connection = pika.BlockingConnection(params)
            logger.info(f"Thread {threading.get_ident()}: Publisher connection successful.")
        return self._thread_local.connection

    def _invalidate_connection(self):
        """Forcefully closes the connection for the current thread."""
        if hasattr(self._thread_local, 'connection') and self._thread_local.connection.is_open:
            self._thread_local.connection.close()
        if hasattr(self._thread_local, 'connection'):
            del self._thread_local.connection
        logger.warning(f"Thread {threading.get_ident()}: Invalidated publisher connection.")

    def publish(self, exchange_name, routing_key, body):
        """Publishes a message with a built-in retry mechanism."""
        attempt = 0
        while attempt < self.max_retries:
            try:
                connection = self._get_connection()
                with connection.channel() as channel:
                    channel.exchange_declare(exchange=exchange_name, exchange_type='topic', durable=True)
                    message_body = json.dumps(body, default=str).encode('utf-8')
                    channel.basic_publish(
                        exchange=exchange_name,
                        routing_key=routing_key,
                        body=message_body,
                        properties=pika.BasicProperties(
                            content_type='application/json',
                            delivery_mode=pika.DeliveryMode.PERSISTENT,
                        )
                    )
                    logger.info(f" [x] Sent to '{routing_key}': '{message_body.decode()[:150]}...' on attempt {attempt + 1}")
                    return
            except (pika.exceptions.AMQPError, OSError) as e:
                logger.warning(f"Publish attempt {attempt + 1} failed: {e}. Invalidating connection and retrying...")
                self._invalidate_connection()
                attempt += 1
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    logger.critical(f"Failed to publish message to '{routing_key}' after {self.max_retries} attempts.")
                    raise

# Create a single, globally accessible instance of the client.
rabbitmq_client = ThreadSafeRabbitMQClient()