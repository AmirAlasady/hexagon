# MS6/app/execution/executor.py

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessage, AIMessageChunk

from app.logging_config import logger
from app.execution.build_context import BuildContext
from app.messaging.publisher import ResultPublisher

class Executor:
    """
    Takes a fully built context and executes the final LangChain runnable.
    This version is completely STATELESS, passing chat history directly
    into each call as required by the microservice architecture.
    """
    
    def __init__(self, context: BuildContext, publisher: ResultPublisher):
        self.context = context
        self.job = context.job
        self.publisher = publisher

    def _get_final_content(self, result) -> str:
        """
        Safely extracts the final string content from a LangChain result,
        which could be a dict (from an agent) or a message object (from a chain).
        """
        if isinstance(result, dict):
            # AgentExecutor returns a dictionary, the final answer is in the 'output' key.
            return result.get('output', '')
        elif hasattr(result, 'content'):
            # Simple chains (prompt | llm) return a message object with a .content attribute.
            return result.content
        return str(result)

    async def run(self):
        """
        The main execution method. It assembles the final runnable,
        invokes it, and handles publishing the results and feedback.
        """
        logger.info(f"[{self.job.id}] Starting final chain execution.")
        final_result = ""

        # 1. Determine the core runnable: an agent if tools exist, otherwise a simple chain.
        if self.context.tools:
            logger.info(f"[{self.job.id}] Assembling AgentExecutor with {len(self.context.tools)} tools.")
            agent = create_tool_calling_agent(self.context.llm, self.context.tools, self.context.prompt_template)
            runnable = AgentExecutor(agent=agent, tools=self.context.tools, verbose=True)
        else:
            logger.info(f"[{self.job.id}] Assembling a simple LLM chain (no tools).")
            runnable = self.context.prompt_template | self.context.llm

        # 2. Add the pre-formatted chat history directly to the input payload.
        #    This makes the execution completely stateless.
        if self.context.memory:
            self.context.final_input["chat_history"] = self.context.memory
            logger.info(f"[{self.job.id}] Added {len(self.context.memory)} messages from history to the input.")
        
        # 3. Execute the chain and handle the output.
        if self.job.is_streaming:
            final_result = await self._stream_and_publish(runnable, self.context.final_input)
        else:
            result = await runnable.ainvoke(self.context.final_input)
            final_result = self._get_final_content(result)
            logger.info(f"[{self.job.id}] FINAL BLOCKING RESPONSE:\n---\n{final_result}\n---")
            await self.publisher.publish_final_result(self.job.id, final_result)
        
        # 4. Trigger the memory feedback loop after the job is fully complete.
        await self.publisher.publish_memory_update(self.job, final_result)

    async def _stream_and_publish(self, chain, input_data: dict) -> str:
        """
        Handles streaming the output and publishing chunks. This is stateless.
        """
        final_result = ""
        logger.info(f"[{self.job.id}] Executing in streaming mode.")
        
        try:
            async for chunk in chain.astream(input_data):
                output_chunk = ""
                if isinstance(chunk, dict):
                    # AgentExecutor yields dicts. The content is in the 'messages' key for streaming.
                    # We look for the content of the last AIMessageChunk.
                    messages = chunk.get('messages', [])
                    if messages and isinstance(messages[-1], AIMessageChunk):
                        output_chunk = messages[-1].content
                elif isinstance(chunk, AIMessageChunk):
                    # Simple chains yield AIMessageChunk objects directly.
                    output_chunk = chunk.content

                if isinstance(output_chunk, str) and output_chunk:
                    await self.publisher.publish_stream_chunk(self.job.id, output_chunk)
                    final_result += output_chunk
        except Exception as e:
            logger.error(f"[{self.job.id}] An error occurred during streaming: {e}", exc_info=True)
            await self.publisher.publish_error_result(self.job.id, f"An error occurred during streaming: {e}")
            return ""
        
        logger.info(f"[{self.job.id}] FINAL STREAMED RESPONSE (concatenated):\n---\n{final_result}\n---")
        await self.publisher.publish_final_result(self.job.id, final_result)
        
        return final_result