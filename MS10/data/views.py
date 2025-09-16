# MS10/data/views.py

from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError

from .models import StoredFile
from .permissions import IsFileOwner
from .services import DataService
from .serializers import StoredFileSerializer, FileUploadSerializer

class FileListCreateAPIView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id):
        service = DataService()
        try:
            files = service.list_files_for_project(
                project_id=project_id,
                user_id=request.user.id,
                jwt_token=str(request.auth)
            )
            serializer = StoredFileSerializer(files, many=True)
            return Response(serializer.data)
        except (PermissionDenied, NotFound) as e:
            return Response({"error": str(e)}, status=e.status_code)

    def post(self, request, project_id):
        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_obj = serializer.validated_data['file']
        
        service = DataService()
        try:
            new_file = service.create_file(
                owner_id=request.user.id,
                project_id=project_id,
                file_obj=file_obj,
                jwt_token=str(request.auth)
            )
            response_serializer = StoredFileSerializer(new_file)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        except (PermissionDenied, NotFound, ValidationError) as e:
            return Response({"error": str(e)}, status=e.status_code)
        except Exception as e:
            return Response({"error": "An unexpected error occurred during file upload."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class FileDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsFileOwner]

    def get_object(self, pk):
        try:
            obj = StoredFile.objects.get(pk=pk)
            # This is still valuable, as it prevents users from even knowing
            # that a file they don't own exists (e.g., for GET requests).
            self.check_object_permissions(self.request, obj)
            return obj
        except StoredFile.DoesNotExist:
            raise NotFound("File not found.")

    def get(self, request, pk):
        instance = self.get_object(pk)
        serializer = StoredFileSerializer(instance)
        return Response(serializer.data)

    # --- THE CORRECTED METHOD IS HERE ---
# OLD MS10/data/views.py (with the bug)
    def delete(self, request, pk):
        instance = self.get_object(pk)
        service = DataService()
        try:
            service.delete_file(
                file_instance=instance, 
                user_id=request.user.id
            )
            # This returns a DRF Response object
            return Response(status=status.HTTP_204_NO_CONTENT) 
        except PermissionDenied as e:
            # This returns a DRF Response object
            return Response({"error": str(e)}, status=e.status_code)
        except Exception:
            # This returns a DRF Response object
            return Response({"error": "An unexpected error occurred..."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)