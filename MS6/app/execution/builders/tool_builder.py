# MS6/app/execution/builders/tool_builder.py

from .base_builder import BaseBuilder
from app.execution.build_context import BuildContext
from app.logging_config import logger
from app.internals.clients import ToolServiceClient
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model
import uuid

# --- NEW: A dedicated class to encapsulate a single tool's execution ---
class MicroserviceToolExecutor:
    """
    A callable class that encapsulates the state and logic needed to execute
    a single tool via a gRPC microservice.
    """
    def __init__(self, client: ToolServiceClient, job_id: str, tool_name: str, required_params: list[str]):
        self.client = client
        self.job_id = job_id
        self.tool_name = tool_name
        self.required_params = required_params

    async def __call__(self, **kwargs):
        """
        This is the async method that LangChain's AgentExecutor will call.
        It accepts the arguments provided by the LLM as keyword arguments.
        """
        arguments = kwargs
        
        # --- SOLVES THE session_id PROBLEM ---
        # If the tool's schema requires a 'session_id' but the LLM didn't provide one,
        # we intelligently inject the job_id as the session identifier.
        if 'session_id' in self.required_params and 'session_id' not in arguments:
            logger.info(f"[{self.job_id}] Injecting job_id as session_id for tool '{self.tool_name}'.")
            arguments['session_id'] = self.job_id
        # --- END OF session_id FIX ---

        tool_call_id = f"{self.job_id}-{self.tool_name}-{uuid.uuid4()}"
        tool_call_payload = [{"id": tool_call_id, "name": self.tool_name, "arguments": arguments}]
        
        logger.info(f"[{self.job_id}] Agent requested to execute tool '{self.tool_name}' with args: {arguments}")
        results = await self.client.execute_tools(tool_call_payload)
        
        output = f"Error: No result from tool '{self.tool_name}'."
        if results and results[0]['status'] == 'success':
            output = results[0]["output"]
        elif results:
            output = f"Error from tool '{self.tool_name}': {results[0]['output']}"

        logger.info(f"[{self.job_id}] Tool '{self.tool_name}' returned: {output[:100]}...")
        return output
# --- END OF NEW CLASS ---


class ToolBuilder(BaseBuilder):
    """
    Creates LangChain-compatible tool objects from tool definitions.
    This definitive version uses a callable class for execution, providing
    clarity, state encapsulation, and intelligent session_id injection.
    """
    def __init__(self):
        self.tool_service_client = ToolServiceClient()

    async def build(self, context: BuildContext) -> BuildContext:
        if not context.job.tool_definitions:
            return context
        
        logger.info(f"[{context.job.id}] Building {len(context.job.tool_definitions)} tools.")
        
        for definition in context.job.tool_definitions:
            tool_name = definition["name"]
            tool_params = definition.get("parameters", {}).get("properties", {})
            required_params = definition.get("parameters", {}).get("required", [])
            
            fields_for_model = {
                param_name: (str, Field(..., description=schema.get("description")))
                for param_name, schema in tool_params.items()
            }
            
            DynamicArgsSchema = create_model(f"{tool_name}ArgsSchema", **fields_for_model)

            # --- THE FIX: Instantiate our executor class for each tool ---
            tool_executor = MicroserviceToolExecutor(
                client=self.tool_service_client,
                job_id=context.job.id,
                tool_name=tool_name,
                required_params=required_params
            )
            # --- END OF FIX ---

            # The 'coroutine' is now an instance of our callable class.
            dynamic_tool = StructuredTool.from_function(
                name=tool_name,
                description=definition["description"],
                args_schema=DynamicArgsSchema,
                coroutine=tool_executor, # <-- Pass the class instance
                verbose=True
            )
            
            context.tools.append(dynamic_tool)

        logger.info(f"[{context.job.id}] Tools built successfully.")
        return context