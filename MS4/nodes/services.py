# in nodes/services.py

from django.conf import settings
from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound
import concurrent.futures
import uuid

# These imports must correctly point to your client, repository, and model files.
from .clients import ProjectServiceClient, ModelServiceClient, ToolServiceClient #, MemoryServiceClient, KnowledgeServiceClient
from .repository import NodeRepository
from .models import Node, NodeStatus

class NodeService:
    """
    The service layer for handling all business logic related to Nodes.
    This is the definitive, synchronous, multi-threaded version.
    """
    def __init__(self):
        # Instantiate all dependencies. In a larger app, this would use dependency injection.
        self.node_repo = NodeRepository()
        self.project_client = ProjectServiceClient()
        self.model_client = ModelServiceClient()
        self.tool_client = ToolServiceClient()
        # self.memory_client = MemoryServiceClient()
        # self.knowledge_client = KnowledgeServiceClient()

    def _validate_resources(self, jwt_token: str, project_id: str, configuration: dict):
        """
        Runs all validation checks against other microservices in parallel using a thread pool.
        """
        # If validation is disabled in settings, skip this entire process.
        if not settings.NODE_SERVICE_VALIDATION_ENABLED:
            return
            
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = []
            
            # --- Submit All Validation Tasks Concurrently ---

            # Task 1: Check project ownership.
    #-->>>>>>>>>>>>>>>>>>     
            futures.append(executor.submit(self.project_client.authorize_user, jwt_token, project_id))
    #-->>>>>>>>>>>>>>>>>>        


            # Task 2: Validate the AI Model.
            model_id = configuration.get("model_config", {}).get("model_id")
            if not model_id:
                raise ValidationError("Configuration must include 'model_config' with a 'model_id'.")
            futures.append(executor.submit(self.model_client.validate_model, jwt_token, model_id))


            # Task 3: Validate the Tools.
            tool_config = configuration.get("tool_config", {})
            if "tool_ids" in tool_config and tool_config["tool_ids"]:
                futures.append(
                    executor.submit(
                        self.tool_client.validate_tools,
                        jwt_token,
                        tool_config["tool_ids"]
                    )
                )

            # Task 3 & 4 (Future): Validate Memory and Knowledge resources.
            # These are commented out but show how to extend the pattern.
            # memory_config = configuration.get("memory_config", {})
            # if memory_config.get("is_enabled", False):
            #     bucket_id = memory_config.get("bucket_id")
            #     if not bucket_id:
            #         raise ValidationError("Memory is enabled, but no 'bucket_id' was provided.")
            #     futures.append(executor.submit(self.memory_client.validate_bucket, jwt_token, project_id, bucket_id))
            
            # knowledge_config = configuration.get("knowledge_config", {})
            # if knowledge_config.get("is_enabled", False):
            #     collection_id = knowledge_config.get("collection_id")
            #     if not collection_id:
            #         raise ValidationError("Knowledge is enabled, but no 'collection_id' was provided.")
            #     futures.append(executor.submit(self.knowledge_client.validate_collection, jwt_token, project_id, collection_id))

            # --- Wait for all tasks to complete and check for any failures ---
            for future in concurrent.futures.as_completed(futures):
                # future.result() will do nothing if the task succeeded, but will
                # re-raise any exception (like PermissionDenied, NotFound) that
                # occurred in the thread, causing this entire method to fail.
                future.result()

    def create_draft_node(self, *, jwt_token: str, user_id: uuid.UUID, project_id: uuid.UUID, name: str) -> Node:
        # 1. Authorize project ownership BEFORE creating anything.
        self.project_client.authorize_user(jwt_token, str(project_id))

        # 2. If authorized, create the draft node.
        # The repository will save it with status='draft' and empty config by default.
        return self.node_repo.create(
            project_id=project_id,
            owner_id=user_id,
            name=name
        )

    # --- NEW METHOD: STAGE 2 ---
    def configure_node_model(self, *, jwt_token: str, node: Node, model_id: uuid.UUID) -> Node:
        # 1. Fetch model capabilities. This also validates user access to the model.
        capabilities = self.model_client.get_model_capabilities(jwt_token, str(model_id))

        # 2. Generate the configuration template based on capabilities.
        master_config = {"model_config": {"model_id": str(model_id)}}
        if "text" in capabilities:
            master_config["memory_config"] = {"is_enabled": False, "bucket_id": None}
            master_config["rag_config"] = {"is_enabled": False, "collection_id": None}
        if "tool_use" in capabilities:
            master_config["tool_config"] = {"tool_ids": []}
        # Add other capability-based configurations here...


        # 3. Update the node with the template and activate it.
        return self.node_repo.update(
            node=node,
            name=node.name, # Name doesn't change here
            configuration=master_config,
            status=NodeStatus.ACTIVE
        )

    # --- UPDATED METHOD: FINAL UPDATE ---
    def update_node(self, *, jwt_token: str, node: Node, name: str, configuration: dict) -> Node:
        """
        The use case for updating an existing node. It intelligently handles
        whether the model has changed, requiring a full template regeneration.
        """
        # --- THE NEW, SMARTER LOGIC STARTS HERE ---
        
        # 1. Extract the new model_id from the user's submitted configuration.
        new_model_id_str = configuration.get("model_config", {}).get("model_id")
        if not new_model_id_str:
            raise ValidationError("The provided configuration must contain a 'model_config' with a 'model_id'.")
            
        # 2. Compare with the node's current model_id.
        current_model_id_str = node.configuration.get("model_config", {}).get("model_id")

        final_configuration = {}
        
        if new_model_id_str != current_model_id_str:
            # --- CASE A: The model has been changed! ---
            # This is a major change. We must regenerate the entire config template.
            print(f"INFO: Model changed for node {node.id}. Regenerating configuration template.")
            
            # a. Fetch capabilities of the NEW model. This also validates access.
            capabilities = self.model_client.get_model_capabilities(jwt_token, new_model_id_str)
            
            # b. Generate the new master template.
            master_config = {"model_config": {"model_id": new_model_id_str}}
            if "text" in capabilities:
                master_config["memory_config"] = {"is_enabled": False, "bucket_id": None}
                master_config["rag_config"] = {"is_enabled": False, "collection_id": None}
            if "tool_use" in capabilities:
                master_config["tool_config"] = {"tool_ids": []}
            
            # c. Intelligently merge the user's *other* provided values into the new template.
            #    For example, if the user also provided new tool_ids, we merge them in.
            if "tool_config" in configuration and "tool_use" in capabilities:
                master_config["tool_config"]["tool_ids"] = configuration.get("tool_config", {}).get("tool_ids", [])
            if "memory_config" in configuration and "text" in capabilities:
                 master_config["memory_config"]["is_enabled"] = configuration.get("memory_config", {}).get("is_enabled", False)
            # Add more merge logic here for other resources...
            
            final_configuration = master_config
        else:
            # --- CASE B: The model is the same. ---
            # This is a simple update. We trust the user is providing the full, valid structure.
            final_configuration = configuration

        # 3. Perform final, comprehensive validation on the resulting configuration.
        self._validate_resources(jwt_token, str(node.project_id), final_configuration)
            
        # 4. If all validations pass, save the changes to the database.
        #    This action always resets the status to ACTIVE.
        return self.node_repo.update(
            node=node,
            name=name,
            configuration=final_configuration,
            status=NodeStatus.ACTIVE
        )


    def get_nodes_for_project(self, project_id: uuid.UUID, user_id: int, jwt_token: str) -> list[Node]:
        """
        The use case for listing all nodes in a project.
        It first authorizes project-level access, then fetches the data.
        """
        # Step 1: Authorize that the user can even view this project's contents.
        self.project_client.authorize_user(jwt_token, str(project_id))
        
        # Step 2: If authorized, retrieve the nodes from the local database.
        return self.node_repo.find_by_project(project_id)
        
    def delete_node(self, node: Node):
        """
        The use case for deleting a node. The view handles ownership check.
        This service delegates the deletion to the repository.
        """
        self.node_repo.delete(node)