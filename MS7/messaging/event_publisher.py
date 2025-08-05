from .rabbitmq_client import rabbitmq_client

class ToolEventPublisher:
    def publish_resource_for_user_deleted(self, user_id: str):
        event_name = "resource.for_user.deleted.ToolService"
        payload = {
            "user_id": str(user_id),
            "service_name": "ToolService"
        }
        rabbitmq_client.publish(
            exchange_name='user_events',
            routing_key=event_name,
            body=payload
        )

tool_event_publisher = ToolEventPublisher()