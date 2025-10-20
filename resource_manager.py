import psutil
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class ResourceManager:
    def __init__(self, initial_concurrency: int = 20):
        self.initial_concurrency = initial_concurrency
        self.current_concurrency = initial_concurrency
        self.last_adjustment_time = 0
        
    async def adjust_concurrency(self, stats: dict) -> Optional[int]:
        """Adjust concurrency based on system resources"""
        current_time = asyncio.get_event_loop().time()
        
        # Only adjust every 30 seconds
        if current_time - self.last_adjustment_time < 30:
            return None
            
        self.last_adjustment_time = current_time
        
        if stats['cpu_percent'] > 80 or stats['memory_percent'] > 80:
            self.current_concurrency = max(5, self.current_concurrency - 5)
            return self.current_concurrency
        elif stats['cpu_percent'] < 50 and stats['memory_percent'] < 60:
            self.current_concurrency = min(self.initial_concurrency, 
                                         self.current_concurrency + 2)
            return self.current_concurrency
            
        return None