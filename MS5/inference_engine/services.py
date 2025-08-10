# MS5/inference_engine/services.py

import uuid
from datetime import datetime
import concurrent.futures
from rest_framework.exceptions import PermissionDenied

# Import all necessary gRPC clients
from inference_internals.clients import (
    NodeServiceClient, 
    ModelServiceClient, 
    ToolServiceClient
    # Future: MemoryServiceClient, RAGServiceClient
)

class InferenceOrchestrationService:
    """
    Acts as a Dynamic Mission Controller for all inference requests.
    It inspects a node's configuration and dynamically gathers all required
    resources in parallel before dispatching a self-contained job.
    """
    def __init__(self):
        # Instantiate clients for communication with other services
        self.node_client = NodeServiceClient()
        self.model_client = ModelServiceClient()
        self.tool_client = ToolServiceClient()
        # self.memory_client = MemoryServiceClient()
        # self.rag_client = RAGServiceClient()

    def process_inference_request(self, node_id: str, user_id: str, query_data: dict):
        # 1. Fetch the node's blueprint and check its status.
        node_details = self.node_client.get_node_details(node_id, user_id)
        
        node_status = node_details.get("status")
        if node_status == "inactive":
            raise PermissionDenied(f"Node {node_id} is inactive because its core model was deleted. Inference is not possible.")
        if node_status == "draft":
            raise PermissionDenied(f"Node {node_id} is a draft and has not been configured with a model yet. Inference is not possible.")
        
        # 2. Dynamically collect all required resources in parallel.
        collected_resources = self._collect_resources_dynamically(
            user_id=user_id,
            configuration=node_details.get("configuration", {})
        )

        # 3. Assemble the final, self-contained job payload.
        job_payload = {
            "job_id": str(uuid.uuid4()),
            "user_id": user_id,
            "node": node_details,
            "query": query_data,
            "resources": collected_resources,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # 4. Publish the job to the queue.
        # This assumes you have an event publisher set up.
        from messaging.event_publisher import inference_job_publisher
        inference_job_publisher.publish_job(job_payload)

        return {"job_id": job_payload["job_id"], "status": "Job submitted successfully."}

    def _collect_resources_dynamically(self, user_id: str, configuration: dict) -> dict:
        """
        Inspects the node configuration and launches parallel gRPC calls
        for all required resources.
        """
        collected_resources = {}
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_resource = {}

            # --- Task: Get Model Configuration (Always Required) ---
            model_id = configuration.get("model_config", {}).get("model_id")
            if not model_id:
                raise ValueError("Node configuration is missing a valid 'model_id'.")
            
            future_model = executor.submit(self.model_client.get_model_configuration, model_id, user_id)
            future_to_resource[future_model] = "model_config"

            # --- Task: Get Tool Definitions (If Present) ---
            tool_config = configuration.get("tool_config", {})
            if tool_config and tool_config.get("tool_ids"):
                future_tools = executor.submit(self.tool_client.get_tool_definitions, tool_config["tool_ids"], user_id)
                future_to_resource[future_tools] = "tools"

            # --- Task: Get Memory Context (If Enabled) ---
            # memory_config = configuration.get("memory_config", {})
            # if memory_config and memory_config.get("is_enabled"):
            #     bucket_id = memory_config.get("bucket_id")
            #     future_memory = executor.submit(self.memory_client.get_history, bucket_id, user_id)
            #     future_to_resource[future_memory] = "memory_context"

            # --- Task: Get RAG Documents (If Enabled) ---
            # rag_config = configuration.get("rag_config", {})
            # if rag_config and rag_config.get("is_enabled"):
            #     collection_id = rag_config.get("collection_id")
            #     future_rag = executor.submit(self.rag_client.retrieve_documents, collection_id, query_data['prompt'], user_id)
            #     future_to_resource[future_rag] = "rag_documents"

            # Wait for all submitted tasks to complete
            for future in concurrent.futures.as_completed(future_to_resource):
                resource_name = future_to_resource[future]
                try:
                    # Store the successful result in our dictionary
                    collected_resources[resource_name] = future.result()
                except Exception as exc:
                    print(f'ERROR: Resource collection for "{resource_name}" failed: {exc}')
                    # Re-raise the exception to fail the entire inference request
                    raise
        
        return collected_resources