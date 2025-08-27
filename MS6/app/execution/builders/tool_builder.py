# This is the file you requested to be commented out but structured.
# We will create a full, working version that uses the gRPC client.
from .base_builder import BaseBuilder
from app.execution.build_context import BuildContext
from app.logging_config import logger
from app.internals.clients import ToolServiceClient
from langchain_core.tools import tool as langchain_tool
from pydantic import BaseModel, Field

class ToolBuilder(BaseBuilder):
    """Creates LangChain-compatible tool objects from definitions."""
    def __init__(self):
        self.tool_service_client = ToolServiceClient()

    async def build(self, context: BuildContext) -> BuildContext:
        if not context.job.tool_definitions:
            logger.info(f"[{context.job.id}] No tools defined. Skipping tool builder.")
            return context
        
        logger.info(f"[{context.job.id}] Building {len(context.job.tool_definitions)} tools.")
        
        for definition in context.job.tool_definitions:
            tool_name = definition["name"]
            
            fields = {
                param_name: (str, Field(..., description=schema.get("description")))
                for param_name, schema in definition.get("parameters", {}).get("properties", {}).items()
            }
            
            DynamicArgsSchema = type(f"{tool_name}ArgsSchema", (BaseModel,), fields)

            # This closure captures the tool_name and the client instance
            async def _execute_tool(**kwargs):
                tool_call = [{"id": "call_1", "name": tool_name, "args": kwargs}]
                logger.info(f"[{context.job.id}] Agent requested to execute tool '{tool_name}' with args: {kwargs}")
                results = await self.tool_service_client.execute_tools(tool_call)
                output = results[0]["output"] if results else f"Error: No result from tool '{tool_name}'."
                logger.info(f"[{context.job.id}] Tool '{tool_name}' returned: {output[:100]}...")
                return output
            
            dynamic_tool = langchain_tool(
                name=tool_name,
                description=definition["description"],
                args_schema=DynamicArgsSchema,
                coroutine=_execute_tool
            )
            context.tools.append(dynamic_tool)

        logger.info(f"[{context.job.id}] Tools built successfully.")
        return context