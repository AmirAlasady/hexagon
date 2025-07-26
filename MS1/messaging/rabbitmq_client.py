# in project_service/messaging/rabbitmq_client.py
import pika
import json
from django.conf import settings

class RabbitMQClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RabbitMQClient, cls).__new__(cls)
            cls._instance._connection = None
            cls._instance._channel = None
        return cls._instance

    def _connect(self):
        """Establishes connection and channel if they don't exist."""
        if not self._connection or self._connection.is_closed:
            # In production, use settings.RABBITMQ_URL or individual host/port/creds
            params = pika.URLParameters('amqp://guest:guest@localhost:5672/')
            self._connection = pika.BlockingConnection(params)
            self._channel = self._connection.channel()
            # Declare exchanges to ensure they exist. This is idempotent.
            self._channel.exchange_declare(exchange='user_events', exchange_type='topic', durable=True)
            self.get_channel()

    def get_channel(self):
        """Returns the channel, ensuring connection is active."""
        self._connect()
        return self._channel

    def publish(self, exchange_name, routing_key, body):
        """Publishes a message to a given exchange with a routing key."""
        channel = self.get_channel()
        
        # Ensure the body is a JSON string
        message_body = json.dumps(body)
        
        channel.basic_publish(
            exchange=exchange_name,
            routing_key=routing_key,
            body=message_body,
            properties=pika.BasicProperties(
                content_type='application/json',
                delivery_mode=2,  # make message persistent
            )
        )
        print(f" [x] Sent '{routing_key}':'{message_body}'")

    def close(self):
        """Closes the connection."""
        if self._connection and self._connection.is_open:
            self._connection.close()
        self._instance = None

# Create a single, globally accessible instance
rabbitmq_client = RabbitMQClient()