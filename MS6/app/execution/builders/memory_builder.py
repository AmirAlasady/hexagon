# Builds the Memory
from .base_builder import BaseBuilder
from app.execution.build_context import BuildContext
from app.logging_config import logger
from langchain.memory import ConversationBufferWindowMemory, ConversationSummaryMemory
from langchain_core.messages import AIMessage, HumanMessage

class MemoryBuilder(BaseBuilder):
    """Instantiates the correct LangChain memory object and loads history."""
    async def build(self, context: BuildContext) -> BuildContext:
        job = context.job
        memory_context = job.memory_context
        
        if not memory_context or not memory_context.get("bucket_id"):
            return context # No memory configured for this job

        memory_type = job.query.get("resource_overrides", {}).get("memory_type") or memory_context.get("memory_type")
        logger.info(f"[{job.id}] Building memory of type: '{memory_type}'.")

        if memory_type == "conversation_buffer_window":
            memory = ConversationBufferWindowMemory(k=10, memory_key="chat_history", return_messages=True)
            # Load history
            for msg in memory_context.get("history", []):
                if msg.get("role") == "user":
                    memory.chat_memory.add_message(HumanMessage(content=msg["content"][0]["text"]))
                elif msg.get("role") == "assistant":
                    memory.chat_memory.add_message(AIMessage(content=msg["content"][0]["text"]))
            context.memory = memory

        elif memory_type == "summary":
            # In a real system, the summary would be pre-calculated by the memory service
            summary_text = memory_context.get("history", [{}])[0].get("content", "")
            memory = ConversationSummaryMemory(llm=context.llm, memory_key="chat_history", return_messages=True)
            memory.buffer = summary_text
            context.memory = memory
        
        else:
            logger.warning(f"[{job.id}] Unsupported memory type '{memory_type}'. Skipping.")
        
        return context