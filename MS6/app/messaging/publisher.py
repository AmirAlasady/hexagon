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

    async def publish_memory_update(self, job, final_result, final_input: dict):
        """
        Triggers the memory feedback loop.
        It uses the `persist_inputs_in_memory` flag to decide what to save as the user's prompt.
        """
        memory_ids = job.feedback_ids
        bucket_id = memory_ids.get("memory_bucket_id")
        
        if not bucket_id:
            logger.info(f"[{job.id}] No memory_bucket_id found in job. Skipping memory update.")
            return

        logger.info(f"[{job.id}] Preparing to publish memory update for bucket: {bucket_id}")

        prompt_to_save = ""
        # Your logic is implemented here:
        if job.persist_inputs_in_memory:
            # The flag is true, so we save the combined prompt with file content.
            prompt_to_save = final_input.get("input", job.prompt_text)
            logger.info(f"[{job.id}] Persistence flag is ON. Saving full context to memory.")
        else:
            # The flag is false (or absent), so we only save the user's original typed prompt.
            prompt_to_save = job.prompt_text
            logger.info(f"[{job.id}] Persistence flag is OFF. Saving original prompt to memory.")
        
        # This part of the logic remains the same, building the rich content object.
        # It now uses the correctly selected prompt_to_save.
        user_message_content = [{"type": "text", "text": prompt_to_save}]
        if not job.persist_inputs_in_memory:
            # If we are NOT persisting, we still add the file references for UI display.
            for inp in job.inputs:
                if inp.get('type') == 'file_id':
                    user_message_content.append({"type": "file_ref", "file_id": inp.get('id')})

        user_message = {"role": "user", "content": user_message_content}

        assistant_content = [{"type": "text", "text": final_result}]
        if isinstance(final_result, dict):
            assistant_content = [final_result]

        assistant_message = {"role": "assistant", "content": assistant_content}
        
        update_payload = {
            "idempotency_key": job.id,
            "memory_bucket_id": bucket_id,
            "messages_to_add": [user_message, assistant_message]
        }
        await self._publish("memory_exchange", "memory.context.update", update_payload)