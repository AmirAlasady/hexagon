# Builds the Prompt Template
from .base_builder import BaseBuilder
from app.execution.build_context import BuildContext
from app.logging_config import logger
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

class PromptBuilder(BaseBuilder):
    """Assembles the final prompt template and input variables."""
    async def build(self, context: BuildContext) -> BuildContext:
        job = context.job
        logger.info(f"[{job.id}] Assembling final prompt.")
        
        # Build context string from RAG and on-the-fly data
        context_str = ""
        if job.rag_docs:
            context_str += "--- Context from Knowledge Base ---\n"
            for doc in job.rag_docs:
                context_str += f"Content: {doc.get('content')}\n\n"
        
        if context.on_the_fly_data:
            context_str += "--- Context from Provided Files ---\n"
            for data in context.on_the_fly_data:
                context_str += f"Content: {data.get('content')}\n\n"

        if context_str:
            final_prompt_text = f"{context_str}Based on the context above, please respond to the following:\n\n{job.prompt_text}"
        else:
            final_prompt_text = job.prompt_text
            
        context.final_prompt_input = {"input": final_prompt_text}

        # Create the prompt template
        messages = [("system", "You are a helpful and intelligent AI assistant.")]
        if context.memory:
            messages.append(MessagesPlaceholder(variable_name="chat_history"))
        
        messages.append(("user", "{input}"))
        
        if context.tools:
            messages.append(MessagesPlaceholder(variable_name="agent_scratchpad"))

        context.prompt_template = ChatPromptTemplate.from_messages(messages)
        logger.info(f"[{job.id}] Prompt assembly complete.")
        return context