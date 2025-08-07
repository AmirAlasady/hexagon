# MS4/messaging/rabbitmq_client.py

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
        if not hasattr(self._thread_local, 'connection') or self._thread_local.connection.is_closed:
            print(f"Thread {threading.get_ident()}: (MS4) No active RabbitMQ connection. Creating new one...")
            try:
                params = pika.URLParameters(settings.RABBITMQ_URL)
                self._thread_local.connection = pika.BlockingConnection(params)
                print(f"Thread {threading.get_ident()}: (MS4) Connection successful.")
            except pika.exceptions.AMQPConnectionError as e:
                print(f"CRITICAL: (MS4) Thread {threading.get_ident()} failed to connect to RabbitMQ: {e}")
                raise
        return self._thread_local.connection

    def publish(self, exchange_name, routing_key, body):
        """
        Publishes a message using a short-lived, dedicated channel.
        This is the safest way to publish from multiple threads.
        """
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
                print(f" [x] (MS4) Sent '{routing_key}':'{message_body}'")
        except (pika.exceptions.AMQPError, OSError) as e:
            print(f"Error publishing message from MS4: {e}.")
            if hasattr(self._thread_local, 'connection'):
                self._thread_local.connection.close()
            raise

rabbitmq_client = RabbitMQClient()