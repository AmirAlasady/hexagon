

# messaging/event_publisher.py
from .rabbitmq_client import rabbitmq_client

class InferenceJobPublisher:
    def publish_job(self, job_payload: dict):
        rabbitmq_client.publish(
            exchange_name='inference_exchange', # Use a dedicated exchange
            routing_key='inference.job.start',  # A specific routing key
            body=job_payload
        )

inference_job_publisher = InferenceJobPublisher()