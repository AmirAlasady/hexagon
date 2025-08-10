# messaging/rabbitmq_client.py (Definitive Resilient Version)

import pika
import json
import threading
import time
from django.conf import settings

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
        """
        Gets or creates a dedicated connection for the current thread.
        """
        if not hasattr(self._thread_local, 'connection') or self._thread_local.connection.is_closed:
            print(f"Thread {threading.get_ident()}: No active RabbitMQ connection. Creating new one...")
            try:
                params = pika.URLParameters(settings.RABBITMQ_URL)
                self._thread_local.connection = pika.BlockingConnection(params)
                print(f"Thread {threading.get_ident()}: Connection successful.")
            except pika.exceptions.AMQPConnectionError as e:
                print(f"CRITICAL: Thread {threading.get_ident()} failed to connect to RabbitMQ: {e}")
                raise
        return self._thread_local.connection

    def _invalidate_connection(self):
        """Forcefully closes and removes the connection for the current thread."""
        if hasattr(self._thread_local, 'connection') and self._thread_local.connection.is_open:
            self._thread_local.connection.close()
        if hasattr(self._thread_local, 'connection'):
            del self._thread_local.connection
        print(f"Thread {threading.get_ident()}: Invalidated RabbitMQ connection.")

    def publish(self, exchange_name, routing_key, body):
        """
        Publishes a message with a built-in retry mechanism.
        """
        attempt = 0
        while attempt < self.max_retries:
            try:
                connection = self._get_connection()
                with connection.channel() as channel:
                    channel.exchange_declare(exchange=exchange_name, exchange_type='topic', durable=True)
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
                    print(f" [x] Sent '{routing_key}':'{message_body}' on attempt {attempt + 1}")
                    return # --- SUCCESS, exit the loop ---

            except (pika.exceptions.AMQPError, OSError) as e:
                print(f"WARN: Publish attempt {attempt + 1} failed: {e}. Invalidating connection and retrying...")
                self._invalidate_connection() # Invalidate the bad connection
                attempt += 1
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay) # Wait before next attempt
                else:
                    print(f"CRITICAL: Failed to publish message after {self.max_retries} attempts.")
                    raise  # Re-raise the final exception

# Create a single, globally accessible instance.
rabbitmq_client = RabbitMQClient()