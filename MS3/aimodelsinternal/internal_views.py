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
            # This method will raise PermissionDenied or ValidationError (NotFound)
            # if the user can't access the model.
            self.service.get_model_by_id(model_id=model_id, user_id=request.user.id)
            
            # If it doesn't raise an exception, the user is authorized.
            return Response(status=status.HTTP_204_NO_CONTENT)
        
        except Exception as e:
            # Let DRF's exception handler format the response (403, 404, etc.)
            raise e

class ModelConfigurationView(APIView):
    """
    Internal-only view for the Inference Orchestrator to get the full,
    un-sanitized, and decrypted configuration for a model.
    """
    permission_classes = [permissions.IsAuthenticated]
    service = AIModelService()

    def get(self, request, model_id):
        """
        Returns the full, raw configuration required for an LLM call.
        """
        try:
            model = self.service.get_model_by_id(model_id=model_id, user_id=request.user.id)
            
            # --- IMPORTANT ---
            # Here we bypass the serializer's sanitization logic.
            # We need to decrypt the configuration before sending it.
            
            # Let's assume the service has a method for this.
            # decrypted_config = self.service.get_decrypted_config(model)
            
            # For now, we'll just return the raw config from the DB.
            # Replace this with your actual decryption logic.
            raw_config = model.configuration 
            
            response_data = {
                "provider": model.provider,
                "configuration": raw_config, # The un-sanitized, decrypted config
                "capabilities": model.capabilities,
            }
            return Response(response_data)

        except Exception as e:
            raise e