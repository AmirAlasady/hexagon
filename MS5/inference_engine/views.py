# MS5/inference_engine/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.exceptions import PermissionDenied, ValidationError

from .serializers import InferenceRequestSerializer
from .services import InferenceOrchestrationService

class InferenceAPIView(APIView):
    """
    The single entry point for initiating an inference job on a configured node.
    It delegates all complex logic to the InferenceOrchestrationService.
    
    Endpoint: POST /ms5/api/v1/nodes/{node_id}/infer/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, node_id):
        """
        Handles the submission of a new inference job.
        
        1. Validates the user's incoming query data.
        2. Passes the request to the service layer for orchestration.
        3. Catches any exceptions (e.g., for invalid nodes, permission issues)
           and formats them into a user-friendly error response.
        """
        # Step 1: Validate the request body (e.g., ensure 'prompt' is present)
        serializer = InferenceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = InferenceOrchestrationService()
        try:
            # Step 2: Delegate the core logic to the service layer
            result = service.process_inference_request(
                node_id=str(node_id),
                user_id=str(request.user.id),
                query_data=serializer.validated_data
            )
            
            # Step 3: Return a success response indicating the job was submitted
            return Response(result, status=status.HTTP_202_ACCEPTED)
        
        # Step 4: Handle specific, known errors gracefully
        except FileNotFoundError as e:
            # This is typically raised by a gRPC client if a resource (node, model, tool) is not found.
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
            
        except PermissionDenied as e:
            # This can be raised by a gRPC client OR by our own service layer
            # (e.g., if the node status is 'inactive' or 'draft').
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
            
        except ValidationError as e:
            # Catches validation errors from other services.
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            # Catch-all for any other unexpected server errors
            print(f"CRITICAL: Unexpected error in inference orchestration for node {node_id}: {e}")
            return Response(
                {"error": "An unexpected server error occurred during job orchestration."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )