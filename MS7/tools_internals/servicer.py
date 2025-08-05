import grpc
from google.protobuf.struct_pb2 import Struct
from django.db.models import Q
import uuid

from .generated import tool_pb2, tool_pb2_grpc
from tools.models import Tool
from tools.executor import tool_executor

class ToolServicer(tool_pb2_grpc.ToolServiceServicer):
    """
    Implements the gRPC service methods for the Tool Service.
    This class is the bridge between gRPC requests and the core application logic.
    """

    def ValidateTools(self, request, context):
        try:
            user_id = uuid.UUID(request.user_id)
            tool_ids = [uuid.UUID(tid) for tid in request.tool_ids]
        except ValueError:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("Invalid UUID format for user_id or tool_ids.")
            return tool_pb2.ValidateToolsResponse()

        if not tool_ids:
            return tool_pb2.ValidateToolsResponse(authorized=True)

        valid_tool_count = Tool.objects.filter(
            Q(is_system_tool=True) | Q(owner_id=user_id),
            id__in=tool_ids
        ).count()

        if valid_tool_count == len(tool_ids):
            return tool_pb2.ValidateToolsResponse(authorized=True)
        else:
            error_msg = "One or more tool IDs are invalid or you do not have permission to use them."
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            context.set_details(error_msg)
            return tool_pb2.ValidateToolsResponse(authorized=False, error_message=error_msg)

    def GetToolDefinitions(self, request, context):
        try:
            user_id = uuid.UUID(request.user_id)
            tool_ids = [uuid.UUID(tid) for tid in request.tool_ids]
        except ValueError:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("Invalid UUID format for user_id or tool_ids.")
            return tool_pb2.GetToolDefinitionsResponse()

        accessible_tools = Tool.objects.filter(
            Q(is_system_tool=True) | Q(owner_id=user_id),
            id__in=tool_ids
        )

        if accessible_tools.count() != len(tool_ids):
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Could not find all requested tools or permission denied for one or more tools.")
            return tool_pb2.GetToolDefinitionsResponse()

        definitions = [tool.definition for tool in accessible_tools]
        
        proto_definitions = []
        for definition_dict in definitions:
            s = Struct()
            s.update(definition_dict)
            proto_definitions.append(s)

        return tool_pb2.GetToolDefinitionsResponse(definitions=proto_definitions)

    def ExecuteMultipleTools(self, request, context):
        tool_calls_list = []
        for call in request.tool_calls:
            try:
                # Convert protobuf Struct to Python dict
                arguments = dict(call.arguments)
            except Exception:
                arguments = {}
            
            tool_calls_list.append({
                'id': call.id,
                'name': call.name,
                'arguments': arguments
            })
        
        results = tool_executor.execute_parallel_tools(tool_calls_list)
        
        proto_results = [tool_pb2.ToolResult(**res) for res in results]
        return tool_pb2.ExecuteMultipleToolsResponse(results=proto_results)