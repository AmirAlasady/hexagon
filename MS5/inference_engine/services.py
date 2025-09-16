# MS5/inference_engine/services.py

import uuid
import json
from datetime import datetime
import concurrent.futures
from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound
import logging

from .ticket_manager import generate_ticket
from inference_internals.clients import (
    NodeServiceClient,
    ModelServiceClient,
    ToolServiceClient,
    MemoryServiceClient,
    DataServiceClient  # <-- Now fully integrated
)
from messaging.event_publisher import inference_job_publisher

logger = logging.getLogger(__name__)


class InferenceOrchestrationService:
    def __init__(self):
        self.node_client = NodeServiceClient()
        self.model_client = ModelServiceClient()
        self.tool_client = ToolServiceClient()
        self.memory_client = MemoryServiceClient()
        self.data_client = DataServiceClient()

    def process_inference_request(self, node_id: str, user_id: str, query_data: dict):
        job_id = str(uuid.uuid4())
        logger.info(f"--- [JOB {job_id}] ORCHESTRATION STARTED ---")
        logger.info(f"    Node ID: {node_id} | User ID: {user_id}")

        # ==============================================================================
        # STAGE 1: PARALLEL DATA FETCHING & VALIDATION GAUNTLET
        # ==============================================================================
        logger.info(f"[{job_id}] Stage 1: Fetching all required resources and metadata in parallel...")

        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Submit the mandatory calls first
            future_node = executor.submit(self.node_client.get_node_details, node_id, user_id)
            
            # Immediately get the result for the node, as we need it for subsequent calls.
            # This is the only blocking call in the initial fetch phase.
            node_details = future_node.result()

            # Now, based on node_details, submit all other metadata/config calls
            node_config = node_details.get("configuration", {})
            model_id = node_config.get("model_config", {}).get("model_id")
            if not model_id:
                raise ValidationError("Node is not configured with a valid model.")

            # Submit model config call
            future_model = executor.submit(self.model_client.get_model_configuration, model_id, user_id)
            
            # Submit file metadata call if files are present in the query
            file_ids_to_validate = [
                inp['id'] for inp in query_data.get("inputs", []) if inp.get('type') == 'file_id'
            ]
            future_files = None
            if file_ids_to_validate:
                future_files = executor.submit(self.data_client.get_file_metadata, file_ids_to_validate, user_id)

            # Wait for the model and file metadata calls to complete
            model_details = future_model.result()
            files_metadata = future_files.result() if future_files else []
        
        logger.info(f"[{job_id}] Stage 1: All initial resources fetched.")

        # Perform the validation gauntlet with all the data we just fetched.
        self._validate_request(query_data, node_details, model_details, files_metadata)
        logger.info(f"[{job_id}] Stage 2: Pre-flight validation passed.")

        # ==============================================================================
        # STAGE 2: DYNAMIC RESOURCE COLLECTION
        # ==============================================================================
        logger.info(f"[{job_id}] Stage 3: Collecting dynamic resources (memory, tools)...")
        # This part remains the same, collecting optional resources like memory and tools.
        collected_resources = self._collect_resources_dynamically(
            job_id, user_id, node_config, model_details, query_data
        )

        # ==============================================================================
        # STAGE 3: JOB ASSEMBLY & DISPATCH
        # ==============================================================================
        logger.info(f"[{job_id}] Stage 4: Assembling and dispatching job payload...")
        job_payload = self._assemble_job_payload(
            job_id, user_id, node_details, query_data, collected_resources
        )
        
        ws_ticket = generate_ticket(job_id=job_payload["job_id"], user_id=user_id)

        inference_job_publisher.publish_job(job_payload)
        logger.info(f"[{job_id}] Stage 5: Job published to queue.")
        logger.info(f"--- [JOB {job_id}] ORCHESTRATION FINISHED ---")

        return {"job_id": job_payload["job_id"], "status": "Job submitted successfully.", "websocket_ticket": ws_ticket}

    def _validate_request(self, query_data: dict, node_details: dict, model_details: dict, files_metadata: list[dict]):
        """
        Performs all pre-flight checks before queueing a job.
        This now includes the file compatibility check.
        """
        # 1. Check Node Status
        node_status = node_details.get("status")
        if node_status in ["inactive", "draft"]:
            raise PermissionDenied(f"Node {node_details.get('id')} is in status '{node_status}' and cannot be used for inference.")
        
        # 2. Check File Compatibility vs. Model Capabilities
        if not files_metadata:
            return  # No files to validate.

        model_capabilities = model_details.get("capabilities", [])
        logger.info(f"[{node_details.get('id')}] Validating file types against model capabilities: {model_capabilities}")

        for file_meta in files_metadata:
            mimetype = file_meta.get('mimetype', '')
            filename = f"File with ID {file_meta.get('file_id')}" # Use ID for error messages

            if mimetype.startswith('image/'):
                if 'image' not in model_capabilities:
                    raise ValidationError(f"{filename} is an image, but the selected model does not support image inputs.")
            elif mimetype in ['application/pdf', 'text/plain'] or mimetype.startswith('text/'):
                if 'text' not in model_capabilities:
                    raise ValidationError(f"{filename} is a text document, but the selected model does not support text inputs.")
            else:
                logger.warning(f"Validation skipped for unsupported mimetype: {mimetype}")
            # Add future checks for 'audio', 'video', etc. here

    def _collect_resources_dynamically(self, job_id: str, user_id: str, node_config: dict, model_details: dict, query_data: dict) -> dict:
        """This function remains the same, collecting non-essential-for-validation resources."""
        collected_resources = {"model_config": model_details}
        overrides = query_data.get("resource_overrides", {})

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_resource = {}
            
            if tool_config := node_config.get("tool_config"):
                if tool_ids := tool_config.get("tool_ids"):
                    future = executor.submit(self.tool_client.get_tool_definitions, tool_ids, user_id)
                    future_to_resource[future] = "tools"

            if memory_config := node_config.get("memory_config"):
                persist_flag = query_data.get("output_config", {}).get("persist_inputs_in_memory", False)
                use_memory = overrides.get("use_memory", memory_config.get("is_enabled", False))
                
                if str(use_memory).lower() == 'true':
                    bucket_id = memory_config.get("bucket_id")
                    if not bucket_id:
                        raise ValidationError("Memory is enabled but no 'bucket_id' is configured.")
                    future = executor.submit(self.memory_client.get_history, bucket_id, user_id)
                    future_to_resource[future] = "memory_context"

            for future in concurrent.futures.as_completed(future_to_resource):
                resource_name = future_to_resource[future]
                try:
                    collected_resources[resource_name] = future.result()
                except Exception as exc:
                    logger.error(f"[{job_id}] --> FAILED to collect resource: '{resource_name}'. Reason: {exc}", exc_info=True)
                    raise RuntimeError(f'Resource collection for "{resource_name}" failed') from exc
        
        return collected_resources

    def _assemble_job_payload(self, job_id: str, user_id: str, node_details: dict, query_data: dict, resources: dict) -> dict:
        """This function remains the same."""
        node_config = node_details.get("configuration", {})
        final_resources = {
            "model_config": resources.get("model_config"),
            "tools": resources.get("tools"),
            "rag_context": resources.get("rag_context"), # For future use
            "memory_context": resources.get("memory_context"),
        }
        return {
            "job_id": job_id,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "query": query_data,
            "default_parameters": node_config.get("model_config", {}).get("parameters", {}),
            "resources": final_resources
        }