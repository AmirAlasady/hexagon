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



# --- MODIFICATION ---
# A global dictionary to hold references to running tasks and their job data.
# Structure: { "job_id": {"task": asyncio.Task, "job": Job} }
RUNNING_JOBS = {}
# --- END OF MODIFICATION ---

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

    # --- THIS ENTIRE METHOD IS REWRITTEN FOR MANUAL ACK/NACK ---
    async def process_message(self, message: aio_pika.IncomingMessage):
        """
        The core logic for processing a single message.
        This version uses manual acknowledgement to robustly handle cancellations.
        """
        job_id = "unknown"
        task = asyncio.current_task()

        try:
            # Step 1: Decode the payload first. If this fails, we can reject it.
            payload = json.loads(message.body.decode())
            job = Job(payload)
            job_id = job.id
            
            # Step 2: Register the job and start processing.
            RUNNING_JOBS[job_id] = {"task": task, "job": job}
            logger.info(f"[{job_id}] Task registered for user '{job.user_id}'. Now processing.")

            build_context = BuildContext(job)
            pipeline = ChainConstructionPipeline(build_context)
            final_context = await pipeline.run()

            executor = Executor(final_context, self.result_publisher)
            await executor.run()
            
            logger.info(f"[{job_id}] Successfully finished processing job.")
            
            # Step 3 (Happy Path): Acknowledge the message upon successful completion.
            await message.ack()

        except asyncio.CancelledError:
            logger.warning(f"[{job_id}] Job execution was INTERRUPTED by cancellation signal.")
            if self.result_publisher:
                await self.result_publisher.publish_error_result(job_id, "Job was cancelled by the user.")
            
            # Step 3 (Cancellation Path): Acknowledge the message to remove it from the queue.
            await message.ack()

        except json.JSONDecodeError:
            logger.error(f"Message body is not valid JSON. Discarding message: {message.body.decode()[:200]}...")
            # Rejecting tells the queue to discard the message (or DLQ it).
            await message.reject(requeue=False)
            
        except Exception as e:
            logger.error(f"[{job_id}] Critical error processing message. Publishing error result.", exc_info=True)
            if self.result_publisher:
                await self.result_publisher.publish_error_result(job_id, f"An unexpected internal executor error occurred: {type(e).__name__}")
            
            # Step 3 (Error Path): Nack the message to requeue it for another try.
            # Set requeue=False if you have a Dead Letter Queue and want to send it there instead.
            await message.nack(requeue=True)
            
        finally:
            # Step 4: Always clean up the task from the registry.
            if job_id in RUNNING_JOBS:
                del RUNNING_JOBS[job_id]
                logger.info(f"[{job_id}] Task de-registered.")
    # --- END OF REWRITTEN METHOD ---

    async def run(self):
        """Starts the worker and listens for messages indefinitely."""
        while True:
            try:
                self.connection = await aio_pika.connect_robust(config.RABBITMQ_URL, loop=asyncio.get_event_loop())
                async with self.connection:
                    self.result_publisher = ResultPublisher(self.connection)
                    channel = await self.connection.channel()
                    
                    await channel.set_qos(prefetch_count=self.prefetch_count)
                    logger.info(f"Worker QoS set to {self.prefetch_count}. Ready to process jobs concurrently.")
                    
                    exchange = await channel.declare_exchange('inference_exchange', aio_pika.ExchangeType.TOPIC, durable=True)
                    queue = await channel.declare_queue('inference_jobs_queue', durable=True)
                    await queue.bind(exchange, 'inference.job.start')
                    
                    logger.info(" [*] Inference Executor Worker is ready and waiting for jobs.")
                    
                    async with queue.iterator() as queue_iter:
                        async for message in queue_iter:
                            asyncio.create_task(self.process_message(message))

            except aio_pika.exceptions.AMQPConnectionError as e:
                logger.error(f"RabbitMQ connection lost: {e}. Retrying in 5 seconds...")
                await asyncio.sleep(5)

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