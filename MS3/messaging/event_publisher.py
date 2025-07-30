from .rabbitmq_client import rabbitmq_client

class AIModelEventPublisher:
    """Publishes events related to the AIModel service."""

    def publish_resource_for_user_deleted(self, user_id: str):
        """
        Publishes a confirmation that all AIModels for a given user
        have been successfully deleted.
        """
        event_name = "resource.for_user.deleted.AIModelService"
        payload = {
            "user_id": str(user_id),
            "service_name": "AIModelService"
        }
        rabbitmq_client.publish(
            exchange_name='user_events',
            routing_key=event_name,
            body=payload
        )

# Create a globally accessible instance
aimodel_event_publisher = AIModelEventPublisher()