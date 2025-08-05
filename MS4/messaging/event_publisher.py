# This file will be very similar to the one in Project Service
# but it publishes a different event.

import json
import pika
from django.conf import settings

# A simplified, direct publisher for this worker's specific need
def publish_event(exchange_name, routing_key, body):
    # In a real app, you'd use a shared client, but this is simple and clear.
    params = pika.URLParameters(settings.RABBITMQ_URL)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    # Ensure exchange exists
    channel.exchange_declare(exchange=exchange_name, exchange_type='topic', durable=True)
    
    channel.basic_publish(
        exchange=exchange_name,
        routing_key=routing_key,
        body=json.dumps(body),
        properties=pika.BasicProperties(content_type='application/json', delivery_mode=2)
    )
    print(f" [x] Client Sent '{routing_key}':'{json.dumps(body)}'")
    connection.close()

class NodeEventPublisher:
    def publish_nodes_for_project_deleted(self, project_id: str):
        event_name = "resource.for_project.deleted.NodeService" # Very specific routing key
        payload = {
            "project_id": str(project_id),
            "service_name": "NodeService" # Self-identifies who is confirming
        }
        publish_event(
            exchange_name='project_events',
            routing_key=event_name,
            body=payload
        )

# Create an instance for our worker to use
node_event_publisher = NodeEventPublisher()