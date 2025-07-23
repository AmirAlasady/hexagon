# in nodes/services.py

from django.conf import settings
from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound
import concurrent.futures
import uuid

# These imports must correctly point to your client, repository, and model files.
from .clients import ProjectServiceClient, ModelServiceClient #, MemoryServiceClient, KnowledgeServiceClient
from .repository import NodeRepository
from .models import Node

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
            futures.append(executor.submit(self.project_client.authorize_user, jwt_token, project_id))
            
            # Task 2: Validate the AI Model.
            model_id = configuration.get("model_config", {}).get("model_id")
            if not model_id:
                raise ValidationError("Configuration must include 'model_config' with a 'model_id'.")
            futures.append(executor.submit(self.model_client.validate_model, jwt_token, model_id))

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

    def create_node(self, *, jwt_token: str, user_id: int, project_id: uuid.UUID, name: str, configuration: dict) -> Node:
        """
        The use case for creating a new node. It handles validation and persistence.
        """
        # The service layer is responsible for calling the validation logic.
        self._validate_resources(jwt_token, str(project_id), configuration)
        
        # If validation succeeds, delegate creation to the repository.
        return self.node_repo.create(
            project_id=project_id,
            owner_id=user_id,
            name=name,
            configuration=configuration
        )

    def update_node(self, *, jwt_token: str, user_id: int, node: Node, name: str, configuration: dict) -> Node:
        """
        The use case for updating an existing node. It also re-validates the new configuration.
        """
        # The view is responsible for the initial ownership check. This service
        # is responsible for validating the new configuration payload.
        self._validate_resources(jwt_token, str(node.project_id), configuration)
            
        # If validation succeeds, delegate the update to the repository.
        return self.node_repo.update(
            node=node,
            name=name,
            configuration=configuration
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