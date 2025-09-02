# MS6/app/execution/builders/model_builder.py

from .base_builder import BaseBuilder
from app.execution.build_context import BuildContext
from app.logging_config import logger
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI

def find_config_value(config: dict, key_to_find: str):
    """
    Recursively searches a nested dictionary for a specific key.
    It prioritizes direct values but will look inside 'properties' and 'default'.
    """
    if not isinstance(config, dict):
        return None

    # Priority 1: Check for the key at the current level
    if key_to_find in config:
        return config[key_to_find]

    # Priority 2: Recursively search through all values in the dictionary
    for key, value in config.items():
        if isinstance(value, dict):
            found = find_config_value(value, key_to_find)
            if found is not None:
                # Special case for blueprints: if we found the key in a 'properties'
                # block, we are looking for its 'default' value.
                if key == 'properties' and isinstance(found, dict) and 'default' in found:
                    return found['default']
                # If it's just a value, return it
                elif not isinstance(found, dict):
                    return found
    return None

class ModelBuilder(BaseBuilder):
    """
    Instantiates the correct LangChain chat model using a dynamic,
    introspective approach to parse any valid configuration structure.
    """
    async def build(self, context: BuildContext) -> BuildContext:
        job = context.job
        model_data = job.model_config
        
        provider = model_data.get("provider")
        config_values = model_data.get("configuration", {})

        final_params = {**job.default_params, **job.param_overrides}
        
        logger.info(f"[{job.id}] Building LLM for provider: '{provider}' using dynamic config parser.")

        if provider == "openai":
            api_key = find_config_value(config_values, "api_key")
            model_name = final_params.pop("model_name", find_config_value(config_values, "model_name")) or "gpt-4o"

            if not api_key:
                raise ValueError(f"Dynamically failed to find 'api_key' in OpenAI configuration.")
            context.llm = ChatOpenAI(api_key=api_key, model=model_name, **final_params)

        elif provider == "ollama" or "ollamaDeepSeek":
            model_name = final_params.pop("model_name", find_config_value(config_values, "model_name"))
            base_url = final_params.pop("base_url", find_config_value(config_values, "base_url"))

            if not model_name or not base_url:
                raise ValueError(f"Dynamically failed to find 'base_url' or 'model_name' in Ollama configuration.")
            
            context.llm = ChatOllama(base_url=base_url, model=model_name, **final_params)
            
        elif provider == "google":
            api_key = find_config_value(config_values, "api_key")
            model_name = final_params.pop("model_name", find_config_value(config_values, "model_name")) or "gemini-pro"
            
            if not api_key:
                 raise ValueError(f"Dynamically failed to find 'api_key' in Google configuration.")
            context.llm = ChatGoogleGenerativeAI(google_api_key=api_key, model=model_name, **final_params)
            
        else:
            raise ValueError(f"Unsupported LLM provider: '{provider}'")
        
        logger.info(f"[{job.id}] LLM '{config_values.get('model_name') or model_name}' on provider '{provider}' built successfully.")
        return context