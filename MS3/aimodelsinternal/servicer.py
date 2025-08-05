from google.protobuf.struct_pb2 import Struct
from rest_framework.exceptions import PermissionDenied, ValidationError
import grpc
# Import the generated gRPC classes and your existing service layer
from . import model_pb2, model_pb2_grpc
from aimodels.services import AIModelService

class ModelServicer(model_pb2_grpc.ModelServiceServicer):
    """
    Implements the gRPC service for AI Models.
    It acts as a bridge between the gRPC requests and the Django service layer.
    """

    def GetModelConfiguration(self, request, context):
        """
        Handles the gRPC request to get a model's full configuration.
        """
        print(f"gRPC [ModelService]: Received GetModelConfiguration request for model_id={request.model_id}")
        
        # Reuse your existing, tested business logic from the service layer!
        service = AIModelService()
        
        try:
            # The get_model_by_id method already contains all the necessary
            # authorization logic (is it a system model? does the user own it?).
            model_instance = service.get_model_by_id(
                model_id=request.model_id,
                user_id=request.user_id
            )
            
            # Here you would add your actual decryption logic.
            # For now, we return the raw config from the database.
            # decrypted_config = service.get_decrypted_config(model_instance)
            decrypted_config = model_instance.configuration

            # Convert the Python dict configuration to a protobuf Struct
            proto_config = Struct()
            proto_config.update(decrypted_config)

            return model_pb2.GetModelConfigurationResponse(
                provider=model_instance.provider,
                configuration=proto_config,
                capabilities=model_instance.capabilities
            )

        except PermissionDenied as e:
            print(f"gRPC [ModelService]: Permission denied - {e}")
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            context.set_details(str(e))
            return model_pb2.GetModelConfigurationResponse()
        except ValidationError as e: # This handles 'Not Found' from your service
            print(f"gRPC [ModelService]: Not found - {e}")
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(str(e))
            return model_pb2.GetModelConfigurationResponse()
        except Exception as e:
            print(f"gRPC [ModelService]: Internal error - {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details('An internal error occurred.')
            return model_pb2.GetModelConfigurationResponse()