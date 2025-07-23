# in nodes/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.exceptions import NotFound

# Import everything needed from the project
from .services import NodeService
from .serializers import NodeSerializer, NodeCreateSerializer, NodeUpdateSerializer
from .permissions import IsOwner
from .repository import NodeRepository # Needed for get_object
import uuid

class NodeListCreateAPIView(APIView):
    """
    Handles listing available nodes within a project and creating a new node.
    - GET /ms4/api/v1/projects/{project_id}/nodes/
    - POST /ms4/api/v1/projects/{project_id}/nodes/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id):
        """
        Handles GET requests to list nodes for a specific project.
        """
        service = NodeService()
        # The project_id from the URL is already a UUID object thanks to the URL converter.
        jwt_token = str(request.auth)
        
        # The service layer handles both authorization and data fetching.
        nodes = service.get_nodes_for_project(
            project_id=project_id, 
            user_id=request.user.id, 
            jwt_token=jwt_token
        )
        
        serializer = NodeSerializer(nodes, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, project_id):
        """
        Handles POST requests to create a new node.
        """
        service = NodeService()
        serializer = NodeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        jwt_token = str(request.auth)
        validated_data = serializer.validated_data
        
        # Call the service to perform validation and creation.
        new_node = service.create_node(
            jwt_token=jwt_token,
            user_id=request.user.id,
            project_id=project_id,
            name=validated_data['name'],
            configuration=validated_data['configuration']
        )
        
        response_serializer = NodeSerializer(new_node)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class NodeDetailAPIView(APIView):
    """
    Handles retrieving, updating, and deleting a specific model instance.
    - GET /ms4/api/v1/nodes/{pk}/
    - PUT /ms4/api/v1/nodes/{pk}/
    - DELETE /ms4/api/v1/nodes/{pk}/
    """
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get_object(self, pk):
        """
        Helper method to fetch a node object by its primary key (pk).
        It also runs DRF's object-level permission checks.
        """
        repo = NodeRepository()
        node = repo.find_by_id(pk)
        if not node:
            raise NotFound("Node not found.")
        
        # This line is crucial for the IsOwner permission to work.
        self.check_object_permissions(self.request, node)
        return node
        
    def get(self, request, pk):
        """
        Handles GET requests to retrieve a single node.
        """
        node = self.get_object(pk)
        serializer = NodeSerializer(node)
        return Response(serializer.data)

    def put(self, request, pk):
        """
        Handles PUT requests to update a node.
        """
        service = NodeService()
        node_to_update = self.get_object(pk)
        
        serializer = NodeUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        validated_data = serializer.validated_data
        jwt_token = str(request.auth)
        
        # Call the service to perform validation and update.
        updated_node = service.update_node(
            jwt_token=jwt_token,
            user_id=request.user.id,
            node=node_to_update,
            name=validated_data['name'],
            configuration=validated_data['configuration']
        )
        
        response_serializer = NodeSerializer(updated_node)
        return Response(response_serializer.data)

    def delete(self, request, pk):
        """
        Handles DELETE requests to remove a node.
        """
        service = NodeService()
        node_to_delete = self.get_object(pk)
        
        # The service layer handles the deletion logic.
        service.delete_node(node_to_delete)
        
        return Response(status=status.HTTP_204_NO_CONTENT)