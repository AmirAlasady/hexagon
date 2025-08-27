from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.runnables.history import RunnableWithMessageHistory
from app.logging_config import logger
from app.execution.build_context import BuildContext
from app.messaging.publisher import ResultPublisher

# In-memory store for chat histories. In production, this should be Redis.
chat_history_store = {}

class Executor:
    """Takes a fully built context and executes the final LangChain runnable."""
    
    def __init__(self, context: BuildContext, publisher: ResultPublisher):
        self.context = context
        self.job = context.job
        self.publisher = publisher

    async def run(self):
        logger.info(f"[{self.job.id}] Starting final chain execution.")

        # Determine the core runnable: an agent if tools exist, otherwise a simple chain.
        if self.context.tools:
            agent = create_tool_calling_agent(self.context.llm, self.context.tools, self.context.prompt_template)
            runnable = AgentExecutor(agent=agent, tools=self.context.tools, verbose=True)
        else:
            runnable = self.context.prompt_template | self.context.llm

        # Wrap the runnable with memory if it was configured.
        if self.context.memory:
            agent_with_memory = RunnableWithMessageHistory(
                runnable,
                # A function that returns the memory object for a given session_id
                lambda session_id: chat_history_store.setdefault(session_id, self.context.memory),
                input_messages_key="input",
                history_messages_key="chat_history",
            )
            
            # The session_id is the memory_bucket_id
            session_config = {"configurable": {"session_id": self.job.memory_context.get("bucket_id")}}
            
            if self.job.is_streaming:
                final_result = await self._stream_and_publish(agent_with_memory, self.context.final_input, session_config)
            else:
                result = await agent_with_memory.ainvoke(self.context.final_input, config=session_config)
                final_result = result.get('output', result.content if hasattr(result, 'content') else str(result))
                await self.publisher.publish_final_result(self.job.id, final_result)
        else:
            # Execute without memory
            if self.job.is_streaming:
                final_result = await self._stream_and_publish(runnable, self.context.final_input, None)
            else:
                result = await runnable.ainvoke(self.context.final_input)
                final_result = result.content if hasattr(result, 'content') else str(result)
                await self.publisher.publish_final_result(self.job.id, final_result)
        
        # Trigger feedback loops after successful execution
        await self.publisher.publish_memory_update(self.job, final_result)

    async def _stream_and_publish(self, chain, input_data, config) -> str:
        """Handles streaming the output and publishing chunks."""
        final_result = ""
        logger.info(f"[{self.job.id}] Executing in streaming mode.")
        async for chunk in chain.astream(input_data, config=config):
            # AgentExecutor returns dicts, simple chains return AIMessage chunks
            output_chunk = chunk.get('output', chunk.content if hasattr(chunk, 'content') else '')
            if output_chunk:
                await self.publisher.publish_stream_chunk(self.job.id, output_chunk)
                final_result += output_chunk
        await self.publisher.publish_final_result(self.job.id, final_result) # Publish a final success message
        return final_result