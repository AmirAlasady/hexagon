# MS10/data/services.py
import os
import uuid
import magic
from django.core.files.uploadedfile import UploadedFile
from django.core.files.storage import default_storage # This is the configured S3 storage
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError

from .models import StoredFile
from data_internals.clients import ProjectServiceClient

class DataService:
    def __init__(self):
        self.project_client = ProjectServiceClient()

    def list_files_for_project(self, *, project_id: uuid.UUID, user_id: uuid.UUID, jwt_token: str):
        self.project_client.authorize_user(jwt_token, str(project_id))
        return StoredFile.objects.filter(project_id=project_id, owner_id=user_id)

    def create_file(self, *, owner_id: uuid.UUID, project_id: uuid.UUID, file_obj: UploadedFile, jwt_token: str) -> StoredFile:
        # 1. Authorize project ownership BEFORE doing anything else.
        self.project_client.authorize_user(jwt_token, str(project_id))
        
        # 2. Define a secure storage path.
        #    Using file_obj.name can be a security risk if it contains path characters like '../'.
        #    We'll sanitize it by taking just the basename.
        safe_filename = os.path.basename(file_obj.name)
        storage_path = f"uploads/{project_id}/{owner_id}/{uuid.uuid4()}-{safe_filename}"
        
        # --- THE DEFINITIVE FIX ---
        # 3. Save the file to our object storage (MinIO/S3).
        #    The `default_storage.save()` method handles the entire upload process
        #    and returns the final path/key of the stored object.
        try:
            actual_path = default_storage.save(storage_path, file_obj)
        except Exception as e:
            # Catch potential Boto3/network errors during upload
            raise ValidationError(f"Could not save file to storage backend: {e}")
        # --- END OF FIX ---
        
        # 4. Use python-magic to get a reliable mimetype.
        file_obj.seek(0)
        mimetype = magic.from_buffer(file_obj.read(2048), mime=True)
        file_obj.seek(0)

        # 5. Create the metadata record in our database.
        stored_file = StoredFile.objects.create(
            owner_id=owner_id,
            project_id=project_id,
            filename=safe_filename, # Use the sanitized filename
            mimetype=mimetype,
            size_bytes=file_obj.size,
            storage_path=actual_path
        )
        return stored_file

    def delete_file(self, *, file_instance: StoredFile, user_id: uuid.UUID):
        if str(file_instance.owner_id) != str(user_id):
            raise PermissionDenied("You do not have permission to delete this file.")

        if default_storage.exists(file_instance.storage_path):
            default_storage.delete(file_instance.storage_path)
            
        file_instance.delete()

