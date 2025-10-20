import psutil
import logging

logger = logging.getLogger("system_monitor")

def get_system_health() -> dict:
    """Get essential system health metrics"""
    memory = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=1)
    
    chrome_processes = [p for p in psutil.process_iter(['name', 'memory_info'])
                       if 'chrome' in p.info['name'].lower()]
    
    chrome_memory = sum(p.info['memory_info'].rss for p in chrome_processes) / (1024 * 1024)
    
    stats = {
        "cpu_percent": cpu_percent,
        "memory_percent": memory.percent,
        "chrome_processes": len(chrome_processes),
        "chrome_memory_mb": chrome_memory
    }
    
    logger.info(f"System Stats - CPU: {cpu_percent}% | "
                f"Memory: {memory.percent}% | "
                f"Chrome instances: {len(chrome_processes)} | "
                f"Chrome memory: {chrome_memory:.0f}MB")
    
    return stats