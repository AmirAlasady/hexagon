from django.shortcuts import render

# Create your views here.
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import InferenceRequestSerializer
from .services import InferenceOrchestrationService
from rest_framework.permissions import IsAuthenticated

class InferenceAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, node_id):
        serializer = InferenceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = InferenceOrchestrationService()
        try:
            result = service.process_inference_request(
                node_id=str(node_id),
                user_id=str(request.user.id),
                query_data=serializer.validated_data
            )
            return Response(result, status=status.HTTP_202_ACCEPTED)
        except (FileNotFoundError, PermissionError) as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response({"error": f"An unexpected error occurred: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)