from .strategies import get_strategy
from inference_internals.clients import NodeServiceClient
from messaging.event_publisher import inference_job_publisher
# Need to import uuid and datetime
import uuid
from datetime import datetime

# Import PermissionDenied exception
from django.core.exceptions import PermissionDenied

class InferenceOrchestrationService:
    def process_inference_request(self, node_id: str, user_id: str, query_data: dict):
        # 1. Authorize and fetch the node's configuration blueprint
        node_client = NodeServiceClient()
        node_details = node_client.get_node_details(node_id, user_id)

        node_status = node_details.get("status")
        if node_status == "inactive":
            raise PermissionDenied("This node is inactive because its core model has been deleted. It cannot be used for inference.")
        elif node_status == "altered":
            # This is optional, but good practice to log.
            print(f"WARNING: Running inference on an altered node (ID: {node_id}). Some functionality may be missing.")

        # 2. Select the appropriate resource collection strategy
        StrategyClass = get_strategy(node_details)
        strategy = StrategyClass(user_id, node_details)

        # 3. Execute the strategy to gather all required resources in parallel
        collected_resources = strategy.collect_resources()

        # 4. Assemble the final, self-contained job payload
        job_payload = {
            "job_id": str(uuid.uuid4()), # Generate a unique ID for this job
            "user_id": user_id,
            "node": node_details,
            "query": query_data,
            "resources": collected_resources,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # 5. Publish the job to the queue
        inference_job_publisher.publish_job(job_payload)

        return {"job_id": job_payload["job_id"], "status": "Job submitted successfully."}

