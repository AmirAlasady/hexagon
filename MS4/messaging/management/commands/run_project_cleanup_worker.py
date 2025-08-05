import pika
import json
import time
from django.core.management.base import BaseCommand
from nodes.models import Node # Import your Node model
from messaging.event_publisher import node_event_publisher
from django.conf import settings

def handle_project_deletion(project_id: str):
    """
    The core business logic for cleaning up nodes.
    This is idempotent.
    """
    print(f" [!] Received request to delete nodes for project: {project_id}")
    
    # Use the Django ORM to delete all nodes belonging to this project
    nodes_deleted, _ = Node.objects.filter(project_id=project_id).delete()
    
    print(f" [✓] Deleted {nodes_deleted} nodes for project {project_id}.")
    
    # After successful deletion, publish the confirmation event.
    node_event_publisher.publish_nodes_for_project_deleted(project_id)


class Command(BaseCommand):
    help = 'Runs a RabbitMQ worker to listen for project deletion events.'

    def handle(self, *args, **options):
        connection = pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))
        channel = connection.channel()

        channel.exchange_declare(exchange='project_events', exchange_type='topic', durable=True)
        
        # Create an exclusive queue for this worker. When the worker disconnects, the queue is deleted.
        # Or, create a named, durable queue if you want messages to persist while the worker is down.
        result = channel.queue_declare(queue='', exclusive=True)
        queue_name = result.method.queue

        # Listen for the specific event
        routing_key = 'project.deletion.initiated'
        channel.queue_bind(exchange='project_events', queue=queue_name, routing_key=routing_key)

        self.stdout.write(' [*] NodeService cleanup worker waiting for messages. To exit press CTRL+C')

        def callback(ch, method, properties, body):
            data = json.loads(body)
            project_id = data.get('project_id')

            if project_id:
                try:
                    handle_project_deletion(project_id)
                except Exception as e:
                    self.stderr.write(f" [!] Error handling project deletion for {project_id}: {e}")
                    # In production, you would add nack logic and a Dead Letter Queue here.
            
            ch.basic_ack(delivery_tag=method.delivery_tag)

        channel.basic_consume(queue=queue_name, on_message_callback=callback)
        channel.start_consuming()