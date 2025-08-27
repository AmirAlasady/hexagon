from .base_builder import BaseBuilder
from app.execution.build_context import BuildContext
from app.internals.clients import DataServiceClient
from app.logging_config import logging
import asyncio

logger = logging.getLogger(__name__)

class DataBuilder(BaseBuilder):
    """Fetches and parses on-the-fly data like user-uploaded files."""
    def __init__(self):
        self.data_client = DataServiceClient()

    async def build(self, context: BuildContext) -> BuildContext:
        if not context.job.inputs:
            return context

        logger.info(f"[{context.job.id}] Fetching content for {len(context.job.inputs)} on-the-fly inputs.")
        
        fetch_tasks = [
            self.data_client.get_file_content(inp['id'])
            for inp in context.job.inputs if inp.get('type') == 'file_id'
        ]
        
        results = await asyncio.gather(*fetch_tasks)
        context.on_the_fly_data = results
        
        logger.info(f"[{context.job.id}] Successfully fetched {len(results)} on-the-fly data item(s).")
        return context