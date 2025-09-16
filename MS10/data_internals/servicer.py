# MS10/data_internals/servicer.py

import grpc
import fitz  # PyMuPDF
import logging
from google.protobuf.struct_pb2 import Struct
from django.core.files.storage import default_storage
from rest_framework.exceptions import PermissionDenied

from . import data_pb2, data_pb2_grpc
from data.models import StoredFile

# Configure a logger for the servicer
logging.basicConfig(level=logging.INFO, format='%(asctime)s - MS10-gRPC - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DataServicer(data_pb2_grpc.DataServiceServicer):
    """
    Implements the full DataService gRPC interface.
    This single class handles requests from all other microservices.
    """

    def GetFileMetadata(self, request, context):
        """
        Handles the fast metadata request from MS5 for validation.
        This method ONLY reads from the database. It does not touch object storage.
        """
        logger.info(f"gRPC [GetFileMetadata]: Received request for {len(request.file_ids)} files from user {request.user_id}.")
        try:
            # Efficiently query for all requested files owned by the user.
            files = StoredFile.objects.filter(id__in=request.file_ids, owner_id=request.user_id)
            
            if files.count() != len(request.file_ids):
                # This check handles both "not found" and "permission denied" in one go.
                # If the count doesn't match, the user either doesn't own one of the files
                # or one of the files doesn't exist.
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("One or more files not found or permission denied.")
                logger.warning(f"gRPC [GetFileMetadata]: Validation failed for user {request.user_id}.")
                return data_pb2.GetFileMetadataResponse()

            # Build the list of metadata objects for the response.
            metadata_list = [
                data_pb2.FileMetadata(
                    file_id=str(f.id),
                    mimetype=f.mimetype,
                    owner_id=str(f.owner_id) # owner_id is not strictly needed by MS5 but good for completeness
                )
                for f in files
            ]
            logger.info(f"gRPC [GetFileMetadata]: Successfully validated and found metadata for {len(metadata_list)} files.")
            return data_pb2.GetFileMetadataResponse(metadata=metadata_list)

        except Exception as e:
            logger.error(f"gRPC [GetFileMetadata]: Internal error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"An internal error occurred: {e}")
            return data_pb2.GetFileMetadataResponse()

    def GetFileContent(self, request, context):
        """
        Handles the content retrieval request from MS6.
        This method reads from the database AND object storage and performs parsing.
        """
        logger.info(f"gRPC [GetFileContent]: Received request for file {request.file_id} from user {request.user_id}.")
        try:
            # First, find the file's metadata record.
            file_instance = StoredFile.objects.get(id=request.file_id)
            
            # Authorize that the user making the request owns the file.
            if str(file_instance.owner_id) != str(request.user_id):
                raise PermissionDenied()

            # If authorized, get the raw file from storage.
            raw_file_stream = default_storage.open(file_instance.storage_path)
            
            # Parse the content based on its type.
            content_payload = self._parse_content(raw_file_stream, file_instance.mimetype, file_instance.storage_path)
            
            # Convert the resulting Python dict into a Protobuf Struct.
            proto_struct = Struct()
            proto_struct.update(content_payload)
            
            logger.info(f"gRPC [GetFileContent]: Successfully parsed and returning content for file {request.file_id}.")
            return data_pb2.GetFileContentResponse(file_id=str(file_instance.id), content=proto_struct)

        except StoredFile.DoesNotExist:
            logger.warning(f"gRPC [GetFileContent]: File not found: {request.file_id}.")
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("File not found.")
            return data_pb2.GetFileContentResponse()
        except PermissionDenied:
            logger.warning(f"gRPC [GetFileContent]: Permission denied for user {request.user_id} on file {request.file_id}.")
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            context.set_details("Permission denied to access this file.")
            return data_pb2.GetFileContentResponse()
        except Exception as e:
            logger.error(f"gRPC [GetFileContent]: Internal error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"An internal error occurred during content retrieval: {e}")
            return data_pb2.GetFileContentResponse()

    def _parse_content(self, file_stream, mimetype, storage_path):
        """Helper function to parse file content based on mimetype."""
        if mimetype == 'application/pdf':
            text = ""
            # PyMuPDF can read from a bytes stream directly
            with fitz.open(stream=file_stream.read(), filetype="pdf") as doc:
                for page in doc:
                    text += page.get_text()
            return {"type": "text_content", "content": text}
        
        elif mimetype.startswith('text/'):
            return {"type": "text_content", "content": file_stream.read().decode('utf-8')}
        
        elif mimetype.startswith('image/'):
            # For images, we don't return the bytes. We return the public URL.
            # MS6's PromptBuilder will know what to do with this URL.
            url = default_storage.url(storage_path)
            return {"type": "image_url", "url": url}
            
        else:
            return {"type": "unsupported", "content": f"File type '{mimetype}' is not supported for content parsing."}