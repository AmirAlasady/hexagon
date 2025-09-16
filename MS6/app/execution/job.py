import uuid
class Job:
    """A data class providing a clean, validated, and DEFENSIVE interface to the raw job payload."""
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
        self.persist_inputs_in_memory = self.output_config.get("persist_inputs_in_memory", False)

        # --- THE DEFENSIVE FIX IS HERE ---
        # Get the resources dictionary, defaulting to an empty dict if it's missing or None.
        self.resources = payload.get("resources") or {}
        # --- END OF FIX ---
        
        self.model_config = self.resources.get("model_config", {})
        self.tool_definitions = self.resources.get("tools")
        self.rag_docs = (self.resources.get("rag_context") or {}).get("documents", [])
        self.memory_context = self.resources.get("memory_context") or {}
    
    @property
    def feedback_ids(self):
        return {
            "memory_bucket_id": self.memory_context.get("bucket_id"),
            "rag_collection_id": (self.resources.get("rag_context") or {}).get("collection_id")
        }