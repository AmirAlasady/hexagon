# gRPC and HTTP clients
import grpc
import httpx
import asyncio
import json
from app import config
#from app.internals.generated import tool_pb2, tool_pb2_grpc
from google.protobuf.json_format import MessageToDict
from google.protobuf.struct_pb2 import Struct
from app.logging_config import logging


from app.internals.generated import tool_pb2, tool_pb2_grpc
from app.internals.generated import data_pb2, data_pb2_grpc
from app.logging_config import logger # Use the correct logger import

class ToolServiceClient:
    """A client for interacting with the gRPC Tool Service (MS7)."""
    
    async def execute_tools(self, tool_calls: list[dict]) -> list[dict]:
        """
        Executes one or more tools in parallel by calling the Tool Service.
        """
        if not config.TOOL_SERVICE_GRPC_URL:
            logger.error("TOOL_SERVICE_GRPC_URL is not set. Cannot execute tools.")
            return [{"status": "error", "output": "Tool Service is not configured."}]

        try:
            async with grpc.aio.insecure_channel(config.TOOL_SERVICE_GRPC_URL) as channel:
                # --- THIS IS THE CRITICAL FIX: UNCOMMENT THE LOGIC ---
                stub = tool_pb2_grpc.ToolServiceStub(channel)
                
                proto_tool_calls = []
                for call in tool_calls:
                    arguments = Struct()
                    args_data = call.get("arguments", {})
                    if isinstance(args_data, dict):
                        arguments.update(args_data)
                    
                    proto_tool_calls.append(tool_pb2.ToolCall(
                        id=call.get("id"),
                        name=call.get("name"),
                        arguments=arguments
                    ))

                request = tool_pb2.ExecuteMultipleToolsRequest(tool_calls=proto_tool_calls)
                logger.info(f"Sending gRPC request to ToolService: ExecuteMultipleTools for {len(proto_tool_calls)} tool(s).")
                response = await stub.ExecuteMultipleTools(request, timeout=30.0)
                
                # Convert the Protobuf response back to a Python list of dicts
                return [
                    {
                        "tool_call_id": res.tool_call_id,
                        "name": res.name,
                        "status": res.status,
                        "output": res.output
                    }
                    for res in response.results
                ]
                # --- END OF FIX ---
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error executing tools: {e.details()}", exc_info=True)
            # Return an error structure that the agent can understand
            return [
                {
                    "tool_call_id": call.get("id"),
                    "name": call.get("name"),
                    "status": "error",
                    "output": f"Error calling tool service: {e.details()}"
                } for call in tool_calls
            ]


class DataServiceClient:
    """A client for fetching the parsed content of on-the-fly files."""
    
    async def get_file_content(self, file_id: str, user_id: str) -> dict:
        """
        Fetches and returns the parsed content of a single file from MS10.
        """
        logger.info(f"Fetching content for file_id: {file_id}")
        try:
            async with grpc.aio.insecure_channel(config.DATA_SERVICE_GRPC_URL) as channel:
                stub = data_pb2_grpc.DataServiceStub(channel)
                request = data_pb2.GetFileContentRequest(file_id=file_id, user_id=user_id)
                response = await stub.GetFileContent(request, timeout=60.0) # Longer timeout for parsing
                
                # Convert the proto Struct back to a Python dict
                return MessageToDict(response.content, preserving_proto_field_name=True)
                
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error fetching content for file {file_id}: {e.details()}")
            return {"type": "error", "content": f"Error fetching file content: {e.details()}"}
        except Exception as e:
            logger.error(f"Unexpected error in DataServiceClient: {e}")
            return {"type": "error", "content": f"Unexpected error fetching file content."}