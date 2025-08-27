# Builds the LLM
from .base_builder import BaseBuilder
from app.execution.build_context import BuildContext
from app.logging_config import logger
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.chat_models import ChatOllama

class ModelBuilder(BaseBuilder):
    """Instantiates the correct LangChain chat model based on the job's provider."""
    async def build(self, context: BuildContext) -> BuildContext:
        job = context.job
        provider = job.model_config.get("provider")
        credentials = job.model_config.get("configuration", {})
        final_params = {**job.default_params, **job.param_overrides}
        
        logger.info(f"[{job.id}] Building LLM for provider: '{provider}'.")

        if provider == "openai":
            context.llm = ChatOpenAI(
                api_key=credentials.get("api_key"),
                model=final_params.pop("model_name", "gpt-4o"),
                streaming=True, **final_params
            )
        elif provider == "anthropic":
            context.llm = ChatAnthropic(
                api_key=credentials.get("anthropic_api_key"),
                model=final_params.pop("model_name", "claude-3-opus-20240229"),
                **final_params
            )
        elif provider == "google":
            context.llm = ChatGoogleGenerativeAI(
                google_api_key=credentials.get("google_api_key"),
                model=final_params.pop("model_name", "gemini-pro"),
                **final_params
            )
        elif provider == "ollama":
            context.llm = ChatOllama(
                base_url=credentials.get("base_url"),
                model=final_params.pop("model_name", "llama3"),
                **final_params
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
        
        logger.info(f"[{job.id}] LLM built successfully.")
        return context