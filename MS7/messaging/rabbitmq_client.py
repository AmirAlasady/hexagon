# messaging/rabbitmq_client.py (Definitive Thread-Safe and Channel-Safe Version)

import pika
import json
import threading
from django.conf import settings

class RabbitMQClient:
    """
    A robust, thread-safe RabbitMQ client that manages connections on a per-thread
    basis and uses a fresh channel for each publishing operation. This is the
    recommended pattern for use in multi-threaded applications like Django.
    """
    _thread_local = threading.local()

    def _get_connection(self):
        """
        Gets or creates a dedicated connection for the current thread.
        This method is the core of the thread-safety mechanism.
        """
        # Check if this thread already has a connection, and if it's open.
        if not hasattr(self._thread_local, 'connection') or self._thread_local.connection.is_closed:
            print(f"Thread {threading.get_ident()}: No active RabbitMQ connection. Creating new one...")
            try:
                params = pika.URLParameters(settings.RABBITMQ_URL)
                self._thread_local.connection = pika.BlockingConnection(params)
                print(f"Thread {threading.get_ident()}: Connection successful.")
            except pika.exceptions.AMQPConnectionError as e:
                print(f"CRITICAL: Thread {threading.get_ident()} failed to connect to RabbitMQ: {e}")
                raise  # Re-raise the exception to signal a failure.
        return self._thread_local.connection

    def publish(self, exchange_name, routing_key, body):
        """
        Publishes a message using a short-lived, dedicated channel.
        This is the safest way to publish from multiple threads.
        """
        try:
            connection = self._get_connection()
            # --- THE CRITICAL FIX IS HERE ---
            # Use a 'with' statement to ensure the channel is always closed,
            # even if errors occur. A new channel is created for every publish.
            with connection.channel() as channel:
                # Ensure the exchange exists. This is idempotent and cheap to call.
                channel.exchange_declare(exchange=exchange_name, exchange_type='topic', durable=True)
    
                message_body = json.dumps(body, default=str)
                
                channel.basic_publish(
                    exchange=exchange_name,
                    routing_key=routing_key,
                    body=message_body,
                    properties=pika.BasicProperties(
                        content_type='application/json',
                        delivery_mode=pika.DeliveryMode.Persistent, # Make message durable
                    )
                )
                print(f" [x] Sent '{routing_key}':'{message_body}'")
        except (pika.exceptions.AMQPError, OSError) as e:
            # Catch a broader range of potential connection/channel errors.
            print(f"Error publishing message: {e}. The connection will be re-established on the next call.")
            # Invalidate the connection so it's forcefully recreated next time.
            if hasattr(self._thread_local, 'connection'):
                self._thread_local.connection.close()
            raise # Re-raise so the calling view knows the publish failed.

# Create a single, globally accessible instance.
rabbitmq_client = RabbitMQClient()