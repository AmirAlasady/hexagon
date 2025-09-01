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

logger = logging.getLogger(__name__)

class ToolServiceClient:
    """A client for interacting with the gRPC Tool Service."""
    
    async def execute_tools(self, tool_calls: list[dict]) -> list[dict]:
        """
        Executes one or more tools in parallel by calling the Tool Service.
        """
        try:
            async with grpc.aio.insecure_channel(config.TOOL_SERVICE_GRPC_URL) as channel:
                #stub = tool_pb2_grpc.ToolServiceStub(channel)
                
                proto_tool_calls = []
                for call in tool_calls:
                    arguments = Struct()
                    # LangChain can sometimes pass stringified JSON, so we handle both dicts and strings.
                    args_data = call.get("args", {})
                    if isinstance(args_data, str):
                        try:
                            args_data = json.loads(args_data)
                        except json.JSONDecodeError:
                            logger.warning(f"Could not decode string arguments for tool {call.get('name')}: {args_data}")
                            args_data = {}
                    
                    if isinstance(args_data, dict):
                        arguments.update(args_data)

                    #proto_tool_calls.append(tool_pb2.ToolCall(
                    #    id=call.get("id"),
                    #    name=call.get("name"),
                    #    arguments=arguments
                    #))

                #request = tool_pb2.ExecuteMultipleToolsRequest(tool_calls=proto_tool_calls)
                #response = await stub.ExecuteMultipleTools(request, timeout=30.0)
                
                return [
                    #{
                    #    "tool_call_id": res.tool_call_id,
                    #    "name": res.name,
                    #    "status": res.status,
                    #    "output": res.output
                    #}
                    #for res in response.results
                ]
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error executing tools: {e.details()}")
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
    """
    A client for fetching the content of on-the-fly files from a data service.
    This is a placeholder and should be adapted to your actual Data Service (MS-Data/RAG).
    """
    
    async def get_file_content(self, file_id: str) -> dict:
        """
        Fetches and parses a file's content.
        """
        logger.info(f"Fetching content for file_id: {file_id}")
        if not config.DATA_SERVICE_URL:
            logger.warning("DATA_SERVICE_URL not set. Returning mock data.")
            await asyncio.sleep(0.1) # Simulate network call
            return {
                "source_id": file_id,
                "type": "text_content",
                "content": f"This is the mock parsed text content of file {file_id}."
            }
            
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # This assumes your Data service has an internal endpoint like this
                response = await client.get(f"{config.DATA_SERVICE_URL}/internal/v1/files/{file_id}/content")
                response.raise_for_status()
                return response.json()
        except httpx.RequestError as e:
            logger.error(f"Could not connect to Data Service to fetch file {file_id}: {e}")
            return {"source_id": file_id, "type": "error", "content": "Could not connect to Data Service."}
        except httpx.HTTPStatusError as e:
            logger.error(f"Data Service returned an error for file {file_id}: {e.response.status_code} {e.response.text}")
            return {"source_id": file_id, "type": "error", "content": f"Error from Data Service: {e.response.status_code}"}