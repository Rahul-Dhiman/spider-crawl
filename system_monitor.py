import psutil
import logging
from typing import Dict

logger = logging.getLogger("system_monitor")

def get_system_health() -> Dict:
    """Get current system health metrics"""
    memory = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=1)
    
    # Get Chrome processes
    chrome_processes = [p for p in psutil.process_iter(['name', 'memory_info'])
                       if 'chrome' in p.info['name'].lower()]
    
    chrome_memory = sum(p.info['memory_info'].rss for p in chrome_processes) / (1024 * 1024)  # MB
    
    stats = {
        "cpu_percent": cpu_percent,
        "memory_percent": memory.percent,
        "memory_available_mb": memory.available / (1024 * 1024),
        "chrome_processes": len(chrome_processes),
        "chrome_memory_mb": chrome_memory
    }
    
    logger.info("System Health Stats:")
    logger.info(f"CPU Usage: {stats['cpu_percent']}%")
    logger.info(f"Memory Usage: {stats['memory_percent']}%")
    logger.info(f"Available Memory: {stats['memory_available_mb']:.2f} MB")
    logger.info(f"Chrome Instances: {stats['chrome_processes']}")
    logger.info(f"Chrome Memory Usage: {stats['chrome_memory_mb']:.2f} MB")
    
    return stats