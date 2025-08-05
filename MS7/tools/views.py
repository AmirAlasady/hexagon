# MS7/tools/views.py

import json
from django.conf import settings
import httpx
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.exceptions import NotFound

from .models import Tool
from .serializers import ToolSerializer, ToolCreateSerializer, ToolUpdateSerializer
from .permissions import IsOwner
from .services import ToolService # <-- Import the service

class ToolListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    
    # --- Using the Service Layer ---
    service = ToolService()

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ToolCreateSerializer
        return ToolSerializer

    def get_queryset(self):
        """Delegates the logic for fetching accessible tools to the service layer."""
        return self.service.get_user_accessible_tools(user_id=self.request.user.id)

    def perform_create(self, serializer):
        """Delegates the creation logic to the service layer."""
        self.service.create_user_tool(
            owner_id=self.request.user.id,
            **serializer.validated_data
        )

class ToolDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    
    # --- Using the Service Layer ---
    service = ToolService()

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return ToolUpdateSerializer
        return ToolSerializer

    def get_object(self):
        """
        Overrides the default get_object to use the service layer for
        permission-aware retrieval.
        """
        tool_id = self.kwargs.get('pk')
        user_id = self.request.user.id
        
        tool = self.service.get_tool_by_id_for_user(tool_id=tool_id, user_id=user_id)
        
        if not tool:
            raise NotFound("Tool not found or you do not have permission to access it.")
        
        # Check object-level write permissions (IsOwner) after retrieving
        self.check_object_permissions(self.request, tool)
        
        return tool

    def destroy(self, request, *args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return Response({"error": "Authorization header missing."}, status=status.HTTP_401_UNAUTHORIZED)

        # STEP 1: GET THE OBJECT AND CHECK PERMISSIONS
        # This will raise a 404 if not found, or a 403 if the user is not the owner.
        # It also implicitly checks if it's a system tool, as the IsOwner permission will fail.
        instance = self.get_object()
        
        # STEP 2: PERFORM THE DELETION
        # This is now safe to do because all checks have passed.
        self.perform_destroy(instance)
        
        # STEP 3: IF DELETION SUCCEEDED, CALL THE CLEANUP HOOK
        try:
            with httpx.Client(timeout=10.0) as client:
                hook_url = f"{settings.NODE_SERVICE_URL}/ms4/api/v1/hooks/resource-deleted/"
                payload = {"resource_type": "tool", "resource_id": str(instance.pk)}
                headers = {"Authorization": auth_header}
                
                response = client.post(hook_url, json=payload, headers=headers)
                response.raise_for_status()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            # Log this as a critical error for monitoring.
            print(f"CRITICAL ALERT: Tool {instance.pk} was deleted, but the Node Service cleanup hook failed: {e}")

        # STEP 4: RETURN SUCCESS
        return Response(status=status.HTTP_204_NO_CONTENT)