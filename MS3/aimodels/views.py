# in aimodels/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.exceptions import ValidationError, PermissionDenied

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
        """ Handles DELETE requests. """
        try:
            self.service.delete_user_model(model_id=pk, user_id=request.user.id)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except (ValidationError, PermissionDenied) as e:
            return Response({"error": str(e)}, status=e.status_code)