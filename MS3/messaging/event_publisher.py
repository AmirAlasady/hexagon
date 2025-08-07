from .rabbitmq_client import rabbitmq_client

class AIModelEventPublisher:
    def publish_model_deleted(self, model_id: str):
        """
        Announces that a model has been permanently deleted.
        """
        rabbitmq_client.publish(
            exchange_name='resource_events',
            routing_key='model.deleted',
            body={"model_id": model_id}
        )

    def publish_capabilities_updated(self, model_id: str, new_capabilities: list):
        """
        Announces that a model's capabilities have changed.
        """
        rabbitmq_client.publish(
            exchange_name='resource_events',
            routing_key='model.capabilities.updated',
            body={"model_id": model_id, "new_capabilities": new_capabilities}
        )

aimodel_event_publisher = AIModelEventPublisher()