# MS5/inference_engine/services.py

import uuid
import json
from datetime import datetime
import concurrent.futures
from rest_framework.exceptions import PermissionDenied, ValidationError
import logging

from .ticket_manager import generate_ticket
from inference_internals.clients import (
    NodeServiceClient, 
    ModelServiceClient, 
    ToolServiceClient,
    MemoryServiceClient
)

# Use Django's logging configuration
logger = logging.getLogger(__name__)

class InferenceOrchestrationService:
    def __init__(self):
        self.node_client = NodeServiceClient()
        self.model_client = ModelServiceClient()
        self.tool_client = ToolServiceClient()
        self.memory_client = MemoryServiceClient()

    def process_inference_request(self, node_id: str, user_id: str, query_data: dict):
        job_id = str(uuid.uuid4())
        logger.info(f"--- [JOB {job_id}] ORCHESTRATION STARTED ---")
        logger.info(f"    Node ID: {node_id} | User ID: {user_id}")

        # 1. Fetch primary sources of truth
        logger.info(f"[{job_id}] Step 1/5: Fetching Node details...")
        node_details = self.node_client.get_node_details(node_id, user_id)
        
        node_config = node_details.get("configuration", {})
        model_id = node_config.get("model_config", {}).get("model_id")
        if not model_id:
            raise ValidationError("Node is not configured with a valid model.")
        
        logger.info(f"[{job_id}] Step 1/5: Fetching Model configuration for model_id: {model_id}...")
        model_details = self.model_client.get_model_configuration(model_id, user_id)
        
        # 2. Perform Validation Gauntlet
        logger.info(f"[{job_id}] Step 2/5: Performing validation gauntlet...")
        self._validate_request(query_data, node_details, model_details)
        logger.info(f"[{job_id}] Validation passed.")
        
        # 3. Dynamically collect resources
        logger.info(f"[{job_id}] Step 3/5: Starting parallel resource collection...")
        collected_resources = self._collect_resources_dynamically(
            job_id, user_id, node_config, model_details, query_data
        )
        logger.info(f"[{job_id}] Resource collection finished.")

        # 4. Assemble job payload
        job_payload = self._assemble_job_payload(
            job_id, user_id, node_details, query_data, collected_resources
        )
        logger.info(f"[{job_id}] Step 4/5: Job payload assembled.")
        # logger.debug(json.dumps(job_payload, indent=2)) # Uncomment for deep debugging
        
        ws_ticket = generate_ticket(job_id=job_payload["job_id"], user_id=user_id)

        # 5. Publish the job
        from messaging.event_publisher import inference_job_publisher
        inference_job_publisher.publish_job(job_payload)
        logger.info(f"[{job_id}] Step 5/5: Job published to queue.")
        logger.info(f"--- [JOB {job_id}] ORCHESTRATION FINISHED ---")

        return {"job_id": job_payload["job_id"], "status": "Job submitted successfully.", "websocket_ticket": ws_ticket}

    def _validate_request(self, query_data: dict, node_details: dict, model_details: dict):
        node_status = node_details.get("status")
        if node_status in ["inactive", "draft"]:
            raise PermissionDenied(f"Node {node_details.get('id')} is in status '{node_status}' and cannot be used for inference.")
        # ... (rest of validation is correct)

    def _collect_resources_dynamically(self, job_id: str, user_id: str, node_config: dict, model_details: dict, query_data: dict) -> dict:
        collected_resources = {"model_config": model_details}
        overrides = query_data.get("resource_overrides", {})

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_resource = {}
            
            # Tool collection
            if tool_config := node_config.get("tool_config"):
                if tool_ids := tool_config.get("tool_ids"):
                    logger.info(f"[{job_id}] Submitting task: GetToolDefinitions for {len(tool_ids)} tool(s).")
                    future = executor.submit(self.tool_client.get_tool_definitions, tool_ids, user_id)
                    future_to_resource[future] = "tools"

            # Memory collection
            if memory_config := node_config.get("memory_config"):
                use_memory = overrides.get("use_memory", memory_config.get("is_enabled", False))
                if str(use_memory).lower() == 'true':
                    bucket_id = memory_config.get("bucket_id")
                    if not bucket_id:
                        raise ValidationError("Memory is enabled but no 'bucket_id' is configured.")
                    logger.info(f"[{job_id}] Submitting task: GetHistory for memory bucket: {bucket_id}")
                    future = executor.submit(self.memory_client.get_history, bucket_id, user_id)
                    future_to_resource[future] = "memory_context" # <-- This key is correct

            logger.info(f"[{job_id}] Awaiting {len(future_to_resource)} resource task(s)...")
            for future in concurrent.futures.as_completed(future_to_resource):
                resource_name = future_to_resource[future]
                try:
                    # THE BUG WAS HERE. The gRPC response IS the value.
                    collected_resources[resource_name] = future.result()
                    logger.info(f"[{job_id}] --> Successfully collected resource: '{resource_name}'")
                except Exception as exc:
                    logger.error(f"[{job_id}] --> FAILED to collect resource: '{resource_name}'. Reason: {exc}")
                    raise RuntimeError(f'Resource collection for "{resource_name}" failed') from exc
        
        return collected_resources

    def _assemble_job_payload(self, job_id: str, user_id: str, node_details: dict, query_data: dict, resources: dict) -> dict:
        node_config = node_details.get("configuration", {})
        final_resources = {
            "model_config": resources.get("model_config"), "tools": resources.get("tools"),
            "rag_context": resources.get("rag_context"), "memory_context": resources.get("memory_context"),
            "on_the_fly_data": []
        }
        return { "job_id": job_id, "user_id": user_id, "timestamp": datetime.utcnow().isoformat(), "query": query_data, "default_parameters": node_config.get("model_config", {}).get("parameters", {}), "resources": final_resources }