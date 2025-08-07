from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from aimodels.services import AIModelService # Use our existing service layer!

class ModelValidationView(APIView):
    """
    Internal-only view for other services to validate if a user can
    access a specific model.
    """
    permission_classes = [permissions.IsAuthenticated]
    service = AIModelService()

    def get(self, request, model_id):
        """
        Uses the service layer's get method, which already contains
        all the necessary permission logic.
        """
        try:
            print(f"Validating access for model_id: {model_id} for user: {request.user.id}")
            # This method will raise PermissionDenied or ValidationError (NotFound)
            # if the user can't access the model.
            self.service.get_model_by_id(model_id=model_id, user_id=request.user.id)
            print(f"Access validated for model_id: {model_id} for user: {request.user.id}")
            # If it doesn't raise an exception, the user is authorized.
            return Response(status=status.HTTP_204_NO_CONTENT)
        
        except Exception as e:
            print(f"Access validation failed for model_id: {model_id} for user: {request.user.id}")
            # Let DRF's exception handler format the response (403, 404, etc.)
            raise e


        



class ModelCapabilitiesView(APIView):
    """
    Internal-only view for other services to quickly fetch the capabilities
    of a model after validating user access.
    """
    permission_classes = [permissions.IsAuthenticated]
    service = AIModelService()

    def get(self, request, model_id):
        try:
            # The service method already validates that the user can access this model
            model = self.service.get_model_by_id(model_id=model_id, user_id=request.user.id)
            
            # Return only the capabilities list
            return Response({"capabilities": model.capabilities}, status=status.HTTP_200_OK)

        except Exception as e:
            # Let DRF's default exception handler format the 403, 404, etc.
            raise e