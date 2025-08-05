# in aimodels/views.py

import json
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.exceptions import ValidationError, PermissionDenied
import httpx
from django.conf import settings

from .models import AIModel
from .services import AIModelService
from .serializers import AIModelSerializer, AIModelCreateSerializer, AIModelUpdateSerializer
from .permissions import IsOwnerOrReadOnly

class AIModelListCreateAPIView(APIView):
    """
    Handles listing available models and creating a new user-owned model.
    Delegates all logic to the AIModelService.
    """
    permission_classes = [permissions.IsAuthenticated]
    service = AIModelService()

    def get(self, request):
        """ Handles GET requests to list models. """
        models = self.service.get_available_models_for_user(user_id=request.user.id)
        serializer = AIModelSerializer(models, many=True)
        return Response(serializer.data)

    def post(self, request):
        """ Handles POST requests to create a new model. """
        serializer = AIModelCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            new_model = self.service.create_user_model(
                owner_id=request.user.id,
                **serializer.validated_data
            )
            response_serializer = AIModelSerializer(new_model)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        except (ValidationError, PermissionDenied) as e:
            # Catch business logic exceptions from the service and format them correctly.
            return Response({"error": str(e)}, status=e.status_code)
        except Exception:
             # Catch any other unexpected errors from the service.
            return Response({"error": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AIModelDetailAPIView(APIView):
    """
    Handles retrieving, updating, and deleting a specific model instance.
    Delegates all logic to the AIModelService.
    """
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    service = AIModelService()

    def get_object(self, pk):
        """
        Helper method to fetch the object from the DB.
        DRF's permission system will automatically run on the returned object.
        """
        try:
            obj = AIModel.objects.get(pk=pk)
        except AIModel.DoesNotExist:
            raise status.HTTP_404_NOT_FOUND
        
        # Manually trigger the permission check for the object.
        self.check_object_permissions(self.request, obj)
        return obj

    def get(self, request, pk):
        """ Handles GET requests to retrieve a single model. """
        try:
            model_instance = self.service.get_model_by_id(model_id=pk, user_id=request.user.id)
            serializer = AIModelSerializer(model_instance)
            return Response(serializer.data)
        except (ValidationError, PermissionDenied) as e:
            return Response({"error": str(e)}, status=e.status_code)

    def put(self, request, pk):
        """ Handles PUT requests to update a model. """
        serializer = AIModelUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            updated_model = self.service.update_user_model(
                model_id=pk,
                user_id=request.user.id,
                **serializer.validated_data
            )
            response_serializer = AIModelSerializer(updated_model)
            return Response(response_serializer.data)
        except (ValidationError, PermissionDenied) as e:
            return Response({"error": str(e)}, status=e.status_code)

    def delete(self, request, pk):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return Response({"error": "Authorization header missing."}, status=status.HTTP_401_UNAUTHORIZED)
        
        # --- THE FIX: REVERSE THE ORDER OF OPERATIONS ---
        
        # STEP 1: ATTEMPT THE DELETION FIRST
        # The service layer contains all the critical business logic and validation.
        try:
            self.service.delete_user_model(model_id=pk, user_id=request.user.id)
        except PermissionDenied as e:
            # This will catch "System models cannot be deleted." and "You do not own this model."
            # The process stops here, and no hook is ever called.
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except ValidationError as e:
            # This will catch "Model not found."
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
            
        # STEP 2: IF DELETION SUCCEEDED, CALL THE CLEANUP HOOK
        # This code is only reached if the model was successfully deleted from the database.
        try:
            with httpx.Client(timeout=10.0) as client:
                hook_url = f"{settings.NODE_SERVICE_URL}/ms4/api/v1/hooks/resource-deleted/"
                payload = {"resource_type": "model", "resource_id": str(pk)}
                headers = {"Authorization": auth_header}
                
                response = client.post(hook_url, json=payload, headers=headers)
                response.raise_for_status()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            # The model was deleted, but the cleanup failed. This is a state that
            # requires monitoring and possibly manual intervention.
            # We should log this as a critical error.
            print(f"CRITICAL ALERT: Model {pk} was deleted, but the Node Service cleanup hook failed: {e}")
            # We still return a success to the user, because the primary resource was deleted.
            # The system will self-heal the next time a user tries to run the node.
            
        # STEP 3: RETURN SUCCESS TO THE USER
        return Response(status=status.HTTP_204_NO_CONTENT)