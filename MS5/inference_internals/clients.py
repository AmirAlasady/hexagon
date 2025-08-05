# inference_internals/clients.py (Updated Version)
import grpc
from django.conf import settings
from google.protobuf.json_format import MessageToDict

# --- THE FIX IS HERE: Import from the 'generated' sub-package ---
from .generated import node_pb2, node_pb2_grpc
from .generated import model_pb2, model_pb2_grpc
from .generated import tool_pb2, tool_pb2_grpc # <-- NEW IMPORT
class NodeServiceClient:
    # ... (The rest of this file remains exactly the same)
    def get_node_details(self, node_id: str, user_id: str) -> dict:
        with grpc.insecure_channel(settings.NODE_SERVICE_GRPC_URL) as channel:
            stub = node_pb2_grpc.NodeServiceStub(channel)
            request = node_pb2.GetNodeDetailsRequest(node_id=node_id, user_id=user_id)
            try:
                response = stub.GetNodeDetails(request, timeout=10)
                return MessageToDict(response)
            except grpc.RpcError as e:
                # ... (error handling code is unchanged)
                if e.code() == grpc.StatusCode.NOT_FOUND:
                    raise FileNotFoundError(f"Node {node_id} not found.")
                if e.code() == grpc.StatusCode.PERMISSION_DENIED:
                    raise PermissionError(f"Permission denied for node {node_id}.")
                raise

class ModelServiceClient:
    # ... (The rest of this class remains exactly the same)
    def get_model_configuration(self, model_id: str, user_id: str) -> dict:
        with grpc.insecure_channel(settings.MODEL_SERVICE_GRPC_URL) as channel:
            stub = model_pb2_grpc.ModelServiceStub(channel)
            request = model_pb2.GetModelConfigurationRequest(model_id=model_id, user_id=user_id)
            try:
                response = stub.GetModelConfiguration(request, timeout=10)
                return MessageToDict(response)
            except grpc.RpcError as e:
                # ... (error handling code is unchanged)
                if e.code() == grpc.StatusCode.NOT_FOUND:
                    raise FileNotFoundError(f"Model {model_id} not found.")
                if e.code() == grpc.StatusCode.PERMISSION_DENIED:
                    raise PermissionError(f"Permission denied for model {model_id}.")
                raise



# --- NEW CLIENT CLASS ---
class ToolServiceClient:
    def get_tool_definitions(self, tool_ids: list[str], user_id: str) -> list[dict]:
        """
        Calls the Tool Service via gRPC to fetch the full definitions for a list of tools.
        """
        with grpc.insecure_channel(settings.TOOL_SERVICE_GRPC_URL) as channel:
            stub = tool_pb2_grpc.ToolServiceStub(channel)
            request = tool_pb2.GetToolDefinitionsRequest(user_id=user_id, tool_ids=tool_ids)
            try:
                response = stub.GetToolDefinitions(request, timeout=10)
                # Convert list of protobuf Structs to list of Python dicts
                return [MessageToDict(definition) for definition in response.definitions]
            except grpc.RpcError as e:
                print(f"gRPC Error calling Tool Service: {e.details()}")
                if e.code() == grpc.StatusCode.NOT_FOUND:
                    raise FileNotFoundError("One or more requested tools were not found.")
                raise