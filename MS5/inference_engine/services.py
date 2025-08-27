# MS5/inference_engine/services.py

import uuid
from datetime import datetime
import concurrent.futures
from rest_framework.exceptions import PermissionDenied, ValidationError

from inference_internals.clients import (
    NodeServiceClient, 
    ModelServiceClient, 
    ToolServiceClient
)

class InferenceOrchestrationService:
    def __init__(self):
        self.node_client = NodeServiceClient()
        self.model_client = ModelServiceClient()
        self.tool_client = ToolServiceClient()
        # self.memory_client = MemoryServiceClient() # Future
        # self.rag_client = RAGServiceClient()     # Future

    def process_inference_request(self, node_id: str, user_id: str, query_data: dict):
        # 1. Fetch the primary sources of truth
        node_details = self.node_client.get_node_details(node_id, user_id)
        node_config = node_details.get("configuration", {})
        model_id = node_config.get("model_config", {}).get("model_id")
        if not model_id:
            raise ValidationError("Node is not configured with a valid model.")
        
        model_details = self.model_client.get_model_configuration(model_id, user_id)
        
        # 2. Perform the "Validation Gauntlet".
        self._validate_request(query_data, node_details, model_details)
        
        # 3. Dynamically collect all required resources.
        collected_resources = self._collect_resources_dynamically(
            user_id=user_id,
            node_config=node_config,
            model_details=model_details,
            query_data=query_data
        )

        # 4. Assemble the final, streamlined job payload.
        job_payload = self._assemble_job_payload(
            user_id=user_id,
            node_details=node_details,
            query_data=query_data,
            resources=collected_resources
        )
        
        # 5. Publish the job.
        from messaging.event_publisher import inference_job_publisher
        inference_job_publisher.publish_job(job_payload)

        return {"job_id": job_payload["job_id"], "status": "Job submitted successfully."}

    def _validate_request(self, query_data: dict, node_details: dict, model_details: dict):
        node_status = node_details.get("status")
        if node_status in ["inactive", "draft"]:
            raise PermissionDenied(f"Node {node_details.get('id')} is in status '{node_status}' and cannot be used for inference.")

        model_capabilities = set(model_details.get("capabilities", []))
        
        for inp in query_data.get("inputs", []):
            if inp["type"] in ["file_id"] and "text" not in model_capabilities:
                raise ValidationError("The selected model does not support text file inputs.")
            if inp["type"] in ["image_url", "image_id"] and "vision" not in model_capabilities:
                raise ValidationError("The selected model does not support image inputs.")
        
        overrides = query_data.get("resource_overrides", {})
        node_config = node_details.get("configuration", {})
        if overrides.get("use_rag") is True and not node_config.get("rag_config"):
            raise ValidationError("RAG was requested but is not configured on this node.")
        if overrides.get("use_memory") is True and not node_config.get("memory_config"):
            raise ValidationError("Memory was requested but is not configured on this node.")

    def _collect_resources_dynamically(self, user_id: str, node_config: dict, model_details: dict, query_data: dict) -> dict:
        collected_resources = {"model_config": model_details}
        overrides = query_data.get("resource_overrides", {})

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_resource = {}
            
            if tool_config := node_config.get("tool_config"):
                if tool_ids := tool_config.get("tool_ids"):
                    future = executor.submit(self.tool_client.get_tool_definitions, tool_ids, user_id)
                    future_to_resource[future] = "tools"

            # Future implementation for Memory and RAG would go here, respecting overrides
            # Example for Memory:
            # if memory_config := node_config.get("memory_config"):
            #     use_memory = overrides.get("use_memory", memory_config.get("is_enabled", False))
            #     if use_memory:
            #         future = executor.submit(self.memory_client.get_history, memory_config["bucket_id"], user_id)
            #         future_to_resource[future] = "memory_context"

            for future in concurrent.futures.as_completed(future_to_resource):
                resource_name = future_to_resource[future]
                try:
                    collected_resources[resource_name] = future.result()
                except Exception as exc:
                    raise RuntimeError(f'Resource collection for "{resource_name}" failed') from exc
        
        return collected_resources

    def _assemble_job_payload(self, user_id: str, node_details: dict, query_data: dict, resources: dict) -> dict:
        node_config = node_details.get("configuration", {})
        x={
            "job_id": str(uuid.uuid4()),
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "query": query_data,
            "default_parameters": node_config.get("model_config", {}).get("parameters", {}),
            "resources": {
                "model_config": resources.get("model_config"),
                "tools": resources.get("tools"),
                "rag_context": resources.get("rag_context"),
                "memory_context": resources.get("memory_context"),
                "on_the_fly_data": []
            }
        }
        print('------------------------')
        print(x)
        return {
            "job_id": str(uuid.uuid4()),
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "query": query_data,
            "default_parameters": node_config.get("model_config", {}).get("parameters", {}),
            "resources": {
                "model_config": resources.get("model_config"),
                "tools": resources.get("tools"),
                "rag_context": resources.get("rag_context"),
                "memory_context": resources.get("memory_context"),
                "on_the_fly_data": []
            }
        }