# MS6/app/messaging/publisher.py

import json
import aio_pika
from app.logging_config import logger

class ResultPublisher:
    """
    Handles publishing all outgoing messages from the executor using aio_pika.
    This version is fully asynchronous and designed to work with an asyncio event loop.
    """
    def __init__(self, connection: aio_pika.RobustConnection):
        if not connection or connection.is_closed:
            raise ValueError("A valid, open aio_pika connection must be provided.")
        self.connection = connection

    async def _publish(self, exchange_name: str, routing_key: str, body: dict):
        """Publishes a message using a new channel from the shared connection."""
        try:
            # Create a new channel for this publishing operation
            async with self.connection.channel() as channel:
                exchange = await channel.declare_exchange(
                    exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
                )
                message = aio_pika.Message(
                    body=json.dumps(body, default=str).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json"
                )
                await exchange.publish(message, routing_key=routing_key)
                logger.info(f"Published message to exchange '{exchange_name}' with key '{routing_key}'")
        except Exception as e:
            logger.error(f"Failed to publish to exchange '{exchange_name}': {e}", exc_info=True)

    async def publish_stream_chunk(self, job_id: str, chunk_content: str):
        """Publishes a streaming chunk of the result."""
        await self._publish(
            "results_exchange", 
            f"inference.result.streaming.{job_id}",
            {"job_id": job_id, "type": "chunk", "content": chunk_content}
        )
    
    async def publish_final_result(self, job_id: str, result_content: str):
        """Publishes the complete, final message."""
        await self._publish(
            "results_exchange", 
            "inference.result.final", 
            {"job_id": job_id, "status": "success", "content": result_content}
        )

    async def publish_error_result(self, job_id: str, error_message: str):
        """Publishes an error message if the job fails."""
        await self._publish(
            "results_exchange", 
            "inference.result.error", 
            {"job_id": job_id, "status": "error", "error": error_message}
        )

    async def publish_memory_update(self, job, final_result: str):
        """Triggers the memory feedback loop."""
        memory_ids = job.feedback_ids
        bucket_id = memory_ids.get("memory_bucket_id")
        
        if not bucket_id:
            logger.info(f"[{job.id}] No memory_bucket_id found in job. Skipping memory update feedback.")
            return

        logger.info(f"[{job.id}] Preparing to publish memory update for bucket: {bucket_id}")
        
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
            "idempotency_key": job.id,
            "memory_bucket_id": bucket_id,
            "messages_to_add": [user_message, assistant_message]
        }
        await self._publish("memory_exchange", "memory.context.update", update_payload)