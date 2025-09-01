# MS6/app/execution/builders/tool_builder.py

from .base_builder import BaseBuilder
from app.execution.build_context import BuildContext
from app.logging_config import logger
from app.internals.clients import ToolServiceClient
from langchain_core.tools import Tool
from pydantic import BaseModel, Field, create_model
import asyncio
import uuid

# --- THE FIX: A placeholder synchronous function ---
def _placeholder_sync_func(*args, **kwargs):
    """
    LangChain's Tool class requires a sync function, even if we only use the async one.
    This placeholder will never be called if the agent is run asynchronously.
    """
    raise NotImplementedError("This tool can only be run asynchronously.")
# --- END OF FIX ---

class ToolBuilder(BaseBuilder):
    """Creates LangChain-compatible tool objects from definitions."""
    def __init__(self):
        self.tool_service_client = ToolServiceClient()

    async def build(self, context: BuildContext) -> BuildContext:
        if not context.job.tool_definitions:
            return context
        
        logger.info(f"[{context.job.id}] Building {len(context.job.tool_definitions)} tools.")
        
        for definition in context.job.tool_definitions:
            tool_name = definition["name"]
            
            fields_for_model = {
                param_name: (str, Field(..., description=schema.get("description")))
                for param_name, schema in definition.get("parameters", {}).get("properties", {
                }).items()
            }
            
            DynamicArgsSchema = create_model(
                f"{tool_name}ArgsSchema",
                **fields_for_model
            )

            async def _execute_tool(**kwargs):
                tool_call_id = f"{context.job.id}-{tool_name}-{uuid.uuid4()}"
                tool_call = [{"id": tool_call_id, "name": tool_name, "args": kwargs}]
                
                logger.info(f"[{context.job.id}] Agent requested to execute tool '{tool_name}' with args: {kwargs}")
                results = await self.tool_service_client.execute_tools(tool_call)
                
                output = f"Error: No result from tool '{tool_name}'."
                if results and results[0]['status'] == 'success':
                    output = results[0]["output"]
                elif results:
                    output = f"Error from tool '{tool_name}': {results[0]['output']}"

                logger.info(f"[{context.job.id}] Tool '{tool_name}' returned: {output[:100]}...")
                return output

            # --- THE FIX: Provide the required 'func' argument ---
            dynamic_tool = Tool(
                name=tool_name,
                description=definition["description"],
                args_schema=DynamicArgsSchema,
                func=_placeholder_sync_func, # <-- Pass the placeholder sync function
                coroutine=_execute_tool,      # <-- Pass the real async function
                verbose=True
            )
            # --- END OF FIX ---
            
            context.tools.append(dynamic_tool)

        logger.info(f"[{context.job.id}] Tools built successfully.")
        return context
        