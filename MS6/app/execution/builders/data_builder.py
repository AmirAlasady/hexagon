# MS6/app/execution/builders/data_builder.py

from .base_builder import BaseBuilder
from app.execution.build_context import BuildContext
from app.internals.clients import DataServiceClient # <-- Import the new gRPC client
from app.logging_config import logger
import asyncio

class DataBuilder(BaseBuilder):
    """
    Fetches and prepares on-the-fly data (e.g., user-uploaded files) for the prompt.
    This now uses a gRPC client to call the Data Service (MS10).
    """
    def __init__(self):
        self.data_client = DataServiceClient()

    async def build(self, context: BuildContext) -> BuildContext:
        if not context.job.inputs:
            return context

        logger.info(f"[{context.job.id}] Fetching content for {len(context.job.inputs)} on-the-fly inputs from Data Service.")
        
        # Create a list of concurrent tasks to fetch content for all files
        fetch_tasks = []
        for inp in context.job.inputs:
            if inp.get('type') == 'file_id' and inp.get('id'):
                task = self.data_client.get_file_content(
                    file_id=inp['id'], 
                    user_id=context.job.user_id
                )
                fetch_tasks.append(task)
        
        if not fetch_tasks:
            return context

        # Run all fetch tasks in parallel
        results = await asyncio.gather(*fetch_tasks)
        context.on_the_fly_data = results
        
        logger.info(f"[{context.job.id}] Successfully fetched and parsed content for {len(results)} on-the-fly data item(s).")
        return context