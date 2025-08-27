# MS6/app/messaging/publisher.py

from app.logging_config import logger
from .rabbitmq_client import rabbitmq_client # <-- Imports the client from the other file

class ResultPublisher:
    """
    Handles publishing all outgoing messages from the executor by using the
    thread-safe RabbitMQ client.
    """
    def _publish(self, exchange_name, routing_key, body):
        try:
            rabbitmq_client.publish(exchange_name, routing_key, body)
        except Exception as e:
            logger.error(f"FINAL ATTEMPT FAILED to publish to exchange '{exchange_name}': {e}", exc_info=True)

    def publish_stream_chunk(self, job_id, chunk_content):
        self._publish(
            "results_exchange", 
            f"inference.result.streaming.{job_id}",
            {"job_id": job_id, "type": "chunk", "content": chunk_content}
        )
    
    def publish_final_result(self, job_id, result_content):
        self._publish(
            "results_exchange", 
            "inference.result.final", 
            {"job_id": job_id, "status": "success", "content": result_content}
        )

    def publish_error_result(self, job_id, error_message):
        self._publish(
            "results_exchange", 
            "inference.result.error", 
            {"job_id": job_id, "status": "error", "error": error_message}
        )

    def publish_memory_update(self, job, final_result: str):
        memory_ids = job.feedback_ids
        bucket_id = memory_ids.get("memory_bucket_id")
        
        if not bucket_id:
            return
            
        user_message = {"role": "user", "content": [{"type": "text", "text": job.prompt_text}]}
        for inp in job.inputs:
            if inp.get('type') == 'file_id':
                user_message['content'].append({"type": "file_ref", "file_id": inp.get('id')})
            elif inp.get('type') == 'image_url':
                user_message['content'].append({"type": "image_ref", "url": inp.get('url')})

        assistant_message = {
            "role": "assistant",
            "content": [{"type": "text", "text": final_result}]
        }
        
        update_payload = {
            "memory_bucket_id": bucket_id,
            "messages_to_add": [user_message, assistant_message]
        }
        self._publish("memory_exchange", "memory.context.update", update_payload)