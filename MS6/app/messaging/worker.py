import pika
import json
import time
import threading
from app import config
from app.logging_config import logger
from app.execution.job import Job
from app.execution.pipeline import ChainConstructionPipeline
from app.execution.executor import Executor
from app.messaging.publisher import ResultPublisher
from app.execution.build_context import BuildContext

class RabbitMQWorker:
    """
    Manages a robust, blocking connection to RabbitMQ to consume inference jobs.
    This runs in its own thread.
    """
    def __init__(self):
        self.connection = None
        self.channel = None
        self.result_publisher = None

    def _connect(self):
        """Establishes a connection to RabbitMQ."""
        logger.info("Attempting to connect to RabbitMQ...")
        params = pika.URLParameters(config.RABBITMQ_URL)
        self.connection = pika.BlockingConnection(params)
        self.channel = self.connection.channel()
        
        # Initialize the thread-safe publisher for sending results
        self.result_publisher = ResultPublisher()

        exchange_name = 'inference_exchange'
        self.channel.exchange_declare(exchange=exchange_name, exchange_type='topic', durable=True)
        
        queue_name = 'inference_jobs_queue'
        self.channel.queue_declare(queue=queue_name, durable=True)
        self.channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key='inference.job.start')
        
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(queue=queue_name, on_message_callback=self._on_message)
        
        logger.info("Successfully connected to RabbitMQ and set up consumer.")

    def _on_message(self, channel, method_frame, header_properties, body):
        """Callback executed for each message received."""
        job_id = "unknown"
        try:
            payload = json.loads(body.decode())
            job = Job(payload)
            job_id = job.id
            logger.info(f"[{job_id}] Received new job. Starting processing in a new thread.")
            
            # --- EXECUTE JOB IN A SEPARATE THREAD ---
            # This prevents a long-running AI job from blocking the RabbitMQ connection heartbeat.
            processing_thread = threading.Thread(
                target=self.process_job,
                args=(job,)
            )
            processing_thread.start()
            
        except json.JSONDecodeError:
            logger.error(f"Message body is not valid JSON: {body.decode()[:200]}...")
            self.result_publisher.publish_error_result(job_id, "Invalid job format received.")
        except Exception:
            logger.error(f"[{job_id}] A critical error occurred before job processing could start.", exc_info=True)
            self.result_publisher.publish_error_result(job_id, "An unexpected internal worker error occurred.")
        
        # Acknowledge the message now that the job has been handed off
        channel.basic_ack(delivery_tag=method_frame.delivery_tag)

    def process_job(self, job: Job):
        """
        The target function for the processing thread. This is where the real work happens.
        """
        try:
            # The Executor now needs to be run with asyncio
            import asyncio
            asyncio.run(self._run_async_executor(job))
        except Exception:
            logger.error(f"[{job.id}] Unhandled exception in async job processor.", exc_info=True)
            self.result_publisher.publish_error_result(job.id, "A fatal error occurred during async execution.")
    
    async def _run_async_executor(self, job: Job):
        """Helper to run the async executor logic from a sync thread."""
        logger.info(f"[{job.id}] Async execution started.")
        build_context = BuildContext(job)
        pipeline = ChainConstructionPipeline(build_context)
        final_context = await pipeline.run()
        executor = Executor(final_context, self.result_publisher)
        await executor.run()
        logger.info(f"[{job.id}] Async execution finished.")


    def run(self):
        """Starts the worker and enters a reconnect loop."""
        while True:
            try:
                self._connect()
                logger.info(" [*] Inference Executor Worker is waiting for jobs. To exit press CTRL+C")
                self.channel.start_consuming()
            except KeyboardInterrupt:
                logger.info("Worker shutting down gracefully.")
                if self.connection and self.connection.is_open:
                    self.connection.close()
                break
            except pika.exceptions.AMQPConnectionError as e:
                logger.error(f"RabbitMQ connection lost: {e}. Reconnecting in 5 seconds...")
                time.sleep(5)