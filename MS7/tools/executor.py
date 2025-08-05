import httpx
import importlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from .models import Tool

class ToolExecutor:
    """
    Handles the dynamic execution of tools based on their definition.
    This class is the single point of entry for running any tool.
    """
    def _execute_internal_function(self, pointer: str, arguments: dict):
        try:
            module_name, func_name = pointer.rsplit('.', 1)
            module = importlib.import_module(module_name)
            func_to_execute = getattr(module, func_name)
            return func_to_execute(**arguments)
        except (ImportError, AttributeError) as e:
            raise RuntimeError(f"Could not find or import internal function: {pointer}. Error: {e}")

    def _execute_webhook(self, config: dict, arguments: dict):
        url = config.get("url")
        if not url:
            raise ValueError("Webhook execution config is missing 'url'.")
        
        # Simple bearer token auth for now; can be expanded.
        headers = {"Content-Type": "application/json"}
        auth_config = config.get("authentication")
        if auth_config and auth_config.get("type") == "bearer":
            # In production, this key would be fetched from a secure vault.
            token = auth_config.get("token") 
            headers["Authorization"] = f"Bearer {token}"
            
        with httpx.Client(timeout=10.0) as client:
            try:
                response = client.post(url, json=arguments)
                response.raise_for_status() # Raise an exception for 4xx/5xx responses
                return response.json()
            except httpx.RequestError as e:
                raise RuntimeError(f"Error calling webhook {url}: {e}")

    def execute_single_tool(self, tool_call: dict) -> dict:
        """Executes one tool call and returns the result."""
        tool_name = tool_call.get("name")
        arguments = tool_call.get("arguments", {})

        try:
            tool = Tool.objects.get(name=tool_name) # Assuming user is already authorized
            execution_config = tool.definition.get("execution", {})
            exec_type = execution_config.get("type")

            if exec_type == "internal_function":
                result_content = self._execute_internal_function(execution_config.get("pointer"), arguments)
            elif exec_type == "webhook":
                result_content = self._execute_webhook(execution_config, arguments)
            else:
                raise ValueError(f"Unknown execution type for tool '{tool_name}': {exec_type}")

            return {
                "tool_call_id": tool_call.get("id"),
                "name": tool_name,
                "status": "success",
                "output": json.dumps(result_content) # Ensure output is a JSON string
            }
        except Exception as e:
            return {
                "tool_call_id": tool_call.get("id"),
                "name": tool_name,
                "status": "error",
                "output": str(e)
            }

    def execute_parallel_tools(self, tool_calls: list[dict]) -> list[dict]:
        """
        Executes a list of tool calls in parallel using a thread pool.
        This is the primary method used by the gRPC servicer.
        """
        results = []
        with ThreadPoolExecutor() as executor:
            future_to_call = {executor.submit(self.execute_single_tool, call): call for call in tool_calls}
            for future in as_completed(future_to_call):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    # This catches errors within the future execution itself
                    call = future_to_call[future]
                    results.append({
                        "tool_call_id": call.get("id"),
                        "name": call.get("name"),
                        "status": "error",
                        "output": f"An unexpected execution error occurred: {e}"
                    })
        return results

# A single instance to be used by the gRPC servicer
tool_executor = ToolExecutor()