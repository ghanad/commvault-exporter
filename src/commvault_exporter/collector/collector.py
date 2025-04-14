from prometheus_client.core import GaugeMetricFamily, REGISTRY
from prometheus_client import start_http_server
from typing import Optional, List, Dict, Any
import time
import logging
from ..commvault_api.client import CommvaultAPIClient
from ..config_handler import ConfigHandler

logger = logging.getLogger(__name__)

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

        # VSA Job metrics
        self.vsa_job_status = GaugeMetricFamily(
            'commvault_vsa_job_status',
            'Status of VSA backup jobs',
            labels=['job_id', 'vm_guid', 'client_name', 'status', 'job_type']
        )
        
        self.vsa_job_duration = GaugeMetricFamily(
            'commvault_vsa_job_duration_seconds',
            'Duration of VSA backup jobs in seconds',
            labels=['job_id', 'vm_guid', 'client_name', 'job_type']
        )

        # SQL Job metrics
        self.sql_job_status = GaugeMetricFamily(
            'commvault_sql_job_status',
            'Status of SQL backup jobs',
            labels=['job_id', 'instance_id', 'database_name', 'status', 'job_type']
        )
        
        self.sql_job_duration = GaugeMetricFamily(
            'commvault_sql_job_duration_seconds',
            'Duration of SQL backup jobs in seconds',
            labels=['job_id', 'instance_id', 'database_name', 'job_type']
        )

    def _collect_system_info(self) -> None:
        """Collect system information metrics"""
        version = self.config.get('commvault', 'version', 'unknown')
        commserve_name = self.config.get('commvault', 'commserve_name', 'unknown')
        self.system_info.add_metric([version, commserve_name], 1)

    def _collect_vsa_jobs(self) -> None:
        """Collect VSA job metrics"""
        vm_guid = self.config.get('commvault', 'vm_guid')
        if not vm_guid:
            logger.warning("No VM GUID configured - skipping VSA job collection")
            return

        try:
            jobs = self.api_client.get(f"/v2/vsa/vm/{vm_guid}/jobs")
            if not jobs:
                return

            for job in jobs:
                job_id = str(job.get('jobId', 'unknown'))
                status = job.get('status', 'unknown').lower()
                job_type = job.get('jobType', 'unknown').lower()
                client_name = job.get('clientName', 'unknown')
                duration = float(job.get('duration', 0))

                status_value = 1 if status == 'completed' else 0
                self.vsa_job_status.add_metric(
                    [job_id, vm_guid, client_name, status, job_type],
                    status_value
                )
                self.vsa_job_duration.add_metric(
                    [job_id, vm_guid, client_name, job_type],
                    duration
                )

        except Exception as e:
            logger.error(f"Failed to collect VSA jobs: {str(e)}")

    def _collect_sql_jobs(self) -> None:
        """Collect SQL job metrics"""
        instance_id = self.config.get('commvault', 'sql_instance_id')
        if not instance_id:
            logger.warning("No SQL instance ID configured - skipping SQL job collection")
            return

        try:
            jobs = self.api_client.get(f"/v2/sql/instance/{instance_id}/history/backup")
            if not jobs:
                return

            for job in jobs:
                job_id = str(job.get('jobId', 'unknown'))
                status = job.get('status', 'unknown').lower()
                job_type = job.get('jobType', 'unknown').lower()
                db_name = job.get('databaseName', 'unknown')
                duration = float(job.get('duration', 0))

                status_value = 1 if status == 'completed' else 0
                self.sql_job_status.add_metric(
                    [job_id, instance_id, db_name, status, job_type],
                    status_value
                )
                self.sql_job_duration.add_metric(
                    [job_id, instance_id, db_name, job_type],
                    duration
                )

        except Exception as e:
            logger.error(f"Failed to collect SQL jobs: {str(e)}")

    def collect(self):
        """Collect Prometheus metrics"""
        start_time = time.time()
        success = 0
        metrics = []
        
        try:
            # Collect system info
            self._collect_system_info()
            metrics.append(self.system_info)
            
            # Collect VSA jobs
            self._collect_vsa_jobs()
            metrics.append(self.vsa_job_status)
            metrics.append(self.vsa_job_duration)
            
            # Collect SQL jobs
            self._collect_sql_jobs()
            metrics.append(self.sql_job_status)
            metrics.append(self.sql_job_duration)
            
            # Add scrape metrics
            metrics.append(self.scrape_success)
            metrics.append(self.scrape_duration)
            
            # Mark as successful
            success = 1
            
            return metrics
            
        except Exception as e:
            logger.error(f"Collection failed: {str(e)}")
            
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