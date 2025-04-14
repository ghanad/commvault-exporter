from prometheus_client.core import GaugeMetricFamily, REGISTRY
from prometheus_client import start_http_server
from typing import Optional, List
import time
from ..commvault_api.client import CommvaultAPIClient
from ..config_handler import ConfigHandler

class CommvaultCollector:
    def __init__(self, config: ConfigHandler):
        self.config = config
        self.api_client = CommvaultAPIClient(config)
        
        # Scrape metrics
        self.scrape_duration = GaugeMetricFamily(
            'commvault_scrape_duration_seconds',
            'Time the Commvault scrape took',
            labels=[]
        )
        
        self.scrape_success = GaugeMetricFamily(
            'commvault_scrape_success',
            'Whether the Commvault scrape succeeded',
            labels=[]
        )
        
        # System info metric
        self.system_info = GaugeMetricFamily(
            'commvault_info',
            'Commvault system information',
            labels=['version', 'commserve_name']
        )

    def _collect_system_info(self) -> None:
        """Collect system information metrics"""
        # TODO: Replace with actual API call when endpoint is identified
        # Currently using placeholder values from config
        version = self.config.get('commvault', 'version', 'unknown')
        commserve_name = self.config.get('commvault', 'commserve_name', 'unknown')
        
        self.system_info.add_metric(
            [version, commserve_name],
            1  # Gauge value is always 1 for info metrics
        )

    def collect(self):
        """Collect Prometheus metrics"""
        start_time = time.time()
        success = 0
        metrics = []
        
        try:
            # Collect system info
            self._collect_system_info()
            metrics.append(self.system_info)
            
            # Add scrape metrics
            metrics.append(self.scrape_success)
            metrics.append(self.scrape_duration)
            
            # Mark as successful
            success = 1
            
            return metrics
            
        except Exception as e:
            # Log error but don't crash - return basic metrics
            pass
            
        finally:
            # Always set scrape duration and success
            duration = time.time() - start_time
            self.scrape_duration.add_metric([], duration)
            self.scrape_success.add_metric([], success)

def start_exporter(config: ConfigHandler):
    """Start the Prometheus exporter"""
    # Register collector
    REGISTRY.register(CommvaultCollector(config))
    
    # Start HTTP server
    start_http_server(config.get('exporter', 'port'))