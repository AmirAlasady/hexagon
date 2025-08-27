import uuid

class Job:
    """A data class providing a clean, validated interface to the raw job payload."""
    def __init__(self, payload: dict):
        if not isinstance(payload, dict):
            raise TypeError("Job payload must be a dictionary.")
        
        self.id = payload.get("job_id", str(uuid.uuid4()))
        self.user_id = payload.get("user_id")

        self.query = payload.get("query", {})
        self.prompt_text = self.query.get("prompt", "")
        self.inputs = self.query.get("inputs", [])
        
        self.default_params = payload.get("default_parameters", {})
        self.param_overrides = self.query.get("parameter_overrides", {})
        
        self.output_config = self.query.get("output_config", {})
        self.is_streaming = self.output_config.get("mode") == "streaming"

        self.resources = payload.get("resources", {})
        self.model_config = self.resources.get("model_config", {})
        self.tool_definitions = self.resources.get("tools") # Can be None
        self.rag_docs = self.resources.get("rag_context", {}).get("documents", [])
        self.memory_context = self.resources.get("memory_context", {})
    
    @property
    def feedback_ids(self):
        return {
            "memory_bucket_id": self.memory_context.get("bucket_id"),
            "rag_collection_id": self.resources.get("rag_context", {}).get("collection_id")
        }