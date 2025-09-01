import asyncio
import json
import aio_pika
from app import config
from app.logging_config import logger
from app.execution.job import Job
from app.execution.build_context import BuildContext
from app.execution.pipeline import ChainConstructionPipeline
from app.execution.executor import Executor
from app.messaging.publisher import ResultPublisher

class RabbitMQWorker:
    """
    Manages the asyncio connection and consumption loop for inference jobs.
    This version is designed for high-throughput, concurrent job processing.
    """
    def __init__(self, prefetch_count: int = 10):
        """
        Initializes the worker.
        Args:
            prefetch_count: The maximum number of jobs this worker can
                            process concurrently.
        """
        self.connection = None
        self.result_publisher = None
        self.prefetch_count = prefetch_count

    async def process_message(self, message: aio_pika.IncomingMessage):
        """
        The core logic for processing a single message from the queue.
        This function is designed to be called as a concurrent task.
        """
        job_id = "unknown"
        try:
            # The 'with' statement ensures the message is acknowledged (ack'd)
            # upon successful completion, or rejected (nack'd) if an unhandled
            # exception occurs, putting it back in the queue for another worker.
            # Change requeue to False to send to a Dead Letter Queue instead.
            async with message.process(requeue=True):
                payload = json.loads(message.body.decode())
                
                job = Job(payload)
                job_id = job.id
                logger.info(f"[{job_id}] Processing new job...")

                build_context = BuildContext(job)
                pipeline = ChainConstructionPipeline(build_context)
                final_context = await pipeline.run()

                executor = Executor(final_context, self.result_publisher)
                await executor.run()
                
                logger.info(f"[{job_id}] Successfully finished processing job.")

        except json.JSONDecodeError:
            logger.error(f"Message body is not valid JSON. Discarding message: {message.body.decode()[:200]}...")
            # We explicitly reject here so it doesn't get requeued.
            await message.reject(requeue=False)
        except Exception as e:
            logger.error(f"[{job_id}] Critical error processing message. Publishing error result.", exc_info=True)
            if self.result_publisher:
                await self.result_publisher.publish_error_result(job_id, f"An unexpected internal executor error occurred: {type(e).__name__}")
            # The message will be requeued due to the 'with' statement's default behavior

    async def run(self):
        """Starts the worker and listens for messages indefinitely."""
        while True:
            try:
                self.connection = await aio_pika.connect_robust(config.RABBITMQ_URL, loop=asyncio.get_event_loop())
                async with self.connection:
                    self.result_publisher = ResultPublisher(self.connection)
                    channel = await self.connection.channel()
                    
                    # Set the Quality of Service: how many messages to pre-fetch.
                    # This is the knob for intra-worker concurrency.
                    await channel.set_qos(prefetch_count=self.prefetch_count)
                    logger.info(f"Worker QoS set to {self.prefetch_count}. Ready to process jobs concurrently.")
                    
                    exchange = await channel.declare_exchange('inference_exchange', aio_pika.ExchangeType.TOPIC, durable=True)
                    queue = await channel.declare_queue('inference_jobs_queue', durable=True)
                    await queue.bind(exchange, 'inference.job.start')
                    
                    logger.info(" [*] Inference Executor Worker is ready and waiting for jobs.")
                    
                    # Use an iterator and create background tasks for true concurrency
                    async with queue.iterator() as queue_iter:
                        async for message in queue_iter:
                            # Schedule the processing of the message as a background task.
                            # The loop does not wait for it to finish and can immediately
                            # fetch the next message up to the prefetch_count limit.
                            asyncio.create_task(self.process_message(message))

            except aio_pika.exceptions.AMQPConnectionError as e:
                logger.error(f"RabbitMQ connection lost: {e}. Retrying in 5 seconds...")
                await asyncio.sleep(5)