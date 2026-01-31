"""
Trinity Backend - Metrics Service
Performance tracking and system monitoring
"""

import time
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Track performance metrics for monitoring and load balancing"""
    
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_tokens_generated = 0
        self.total_latency_ms = 0
        self.active_requests = 0
        self.start_time = time.time()
    
    def record_request(self, success: bool, tokens: int, latency_ms: float):
        """Record metrics for a completed request"""
        self.total_requests += 1
        if success:
            self.successful_requests += 1
            self.total_tokens_generated += tokens
            self.total_latency_ms += latency_ms
        else:
            self.failed_requests += 1
    
    def start_request(self):
        """Increment active request counter"""
        self.active_requests += 1
    
    def end_request(self):
        """Decrement active request counter"""
        self.active_requests = max(0, self.active_requests - 1)
    
    def get_stats(self) -> Dict:
        """Get current statistics"""
        uptime = time.time() - self.start_time
        avg_latency = (self.total_latency_ms / self.successful_requests 
                      if self.successful_requests > 0 else 0)
        
        return {
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'success_rate': (self.successful_requests / self.total_requests * 100 
                            if self.total_requests > 0 else 100),
            'total_tokens_generated': self.total_tokens_generated,
            'avg_latency_ms': avg_latency,
            'active_requests': self.active_requests,
            'uptime_seconds': uptime,
        }


# Global metrics instance
metrics = MetricsCollector()


def get_system_info() -> Dict:
    """Get system resource information (CPU, memory)"""
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        
        return {
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'memory_available_mb': memory.available / (1024 * 1024),
        }
    except ImportError:
        logger.warning("psutil not installed - system metrics unavailable")
        return {
            'cpu_percent': 0,
            'memory_percent': 0,
            'memory_available_mb': 0,
        }
