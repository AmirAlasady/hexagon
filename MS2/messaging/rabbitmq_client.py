# project service/messaging/rabbitmq_client.py

import pika
import json
import time
from django.conf import settings
import threading

class RabbitMQClient:
    """
    A thread-safe RabbitMQ client that ensures one connection per thread.
    This prevents connection sharing issues between the main web server thread
    and background worker threads.
    """
    _thread_local = threading.local()

    def _get_connection(self):
        """Gets or creates a connection for the current thread."""
        if not hasattr(self._thread_local, 'connection') or self._thread_local.connection.is_closed:
            print(f"Thread {threading.get_ident()}: No active connection. Connecting to RabbitMQ...")
            try:
                params = pika.URLParameters('amqp://guest:guest@localhost:5672/') # In prod, use settings.RABBITMQ_URL
                self._thread_local.connection = pika.BlockingConnection(params)
                print(f"Thread {threading.get_ident()}: Connection successful.")
            except pika.exceptions.AMQPConnectionError as e:
                print(f"CRITICAL: Failed to connect to RabbitMQ: {e}")
                # In a real app, this should raise an exception or have a retry mechanism.
                raise
        return self._thread_local.connection

    def publish(self, exchange_name, routing_key, body):
        """Publishes a message, ensuring a valid connection and channel."""
        try:
            connection = self._get_connection()
            channel = connection.channel()
            
            # Declare exchanges to ensure they exist. This is idempotent.
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
            print(f" [x] Sent '{routing_key}':'{message_body}'")
        except pika.exceptions.AMQPError as e:
            print(f"Error publishing message: {e}. Connection may be closed. It will be reopened on next call.")
            # Invalidate the connection so it's recreated on the next call
            if hasattr(self._thread_local, 'connection'):
                self._thread_local.connection.close()
            raise # Re-raise the exception so the caller knows the publish failed

# Create a single, globally accessible instance.
# The instance itself is shared, but the connection it manages is thread-local.
rabbitmq_client = RabbitMQClient()