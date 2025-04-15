from prometheus_client.core import GaugeMetricFamily, REGISTRY
from prometheus_client import start_http_server
from typing import List, Dict, Any
import time
import logging
import concurrent.futures
from ..commvault_api.client import CommvaultAPIClient
from ..config_handler import ConfigHandler

logger = logging.getLogger(__name__)

class CommvaultCollector:
    def __init__(self, config: ConfigHandler):
        logger.debug(f"Collector received config type: {type(config)}, str representation: {str(config)[:200]}")
        if not isinstance(config, ConfigHandler):
            raise ValueError(f"Expected ConfigHandler, got {type(config)}")
        self.config = config
        logger.debug(f"Config object contents: {self.config.config}")
        self.api_client = CommvaultAPIClient(config)
        
        # Initialize metrics
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
        
        self.system_info = GaugeMetricFamily(
            'commvault_info',
            'Commvault system information',
            labels=['version', 'commserve_name']
        )

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
        try:
            version = self.config.get('commvault', 'version', default='unknown')
            
            # Get commserve name from config
            commserve_name = self.config.get('commvault', 'commserve_name', default='unknown')
            
            self.system_info.add_metric([version, commserve_name], 1)
            logger.debug(f"Collected system info - Version: {version}, Server: {commserve_name}")
        except Exception as e:
            logger.error(f"Failed to collect system info: {str(e)}")
            raise

    def _collect_vsa_jobs(self) -> None:
        """Collect VSA job metrics"""
        vm_guid = self.config.get('commvault', 'vm_guid', default=None)
        if not vm_guid:
            logger.warning("Skipping VSA job collection - no VM GUID configured")
            return

        try:
            logger.debug(f"Starting VSA job collection for VM: {vm_guid}")
            jobs = self.api_client.get(f"/v2/vsa/vm/{vm_guid}/jobs")
            
            if not jobs:
                logger.debug(f"No VSA jobs found for VM: {vm_guid}")
                return

            for job in jobs:
                try:
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
                    logger.debug(f"Processed VSA job {job_id} with status {status}")
                except (KeyError, ValueError) as e:
                    logger.warning(f"Skipping malformed VSA job entry: {str(e)}")
                    continue

            logger.info(f"Successfully collected {len(jobs)} VSA jobs for VM: {vm_guid}")
        except Exception as e:
            logger.error(f"VSA job collection failed for VM {vm_guid}: {str(e)}")
            raise

    def _collect_sql_jobs(self) -> None:
        """Collect SQL job metrics"""
        instance_id = self.config.get('commvault', 'sql_instance_id', default=None)
        if not instance_id:
            logger.warning("Skipping SQL job collection - no instance ID configured")
            return

        try:
            logger.debug(f"Starting SQL job collection for instance: {instance_id}")
            jobs = self.api_client.get(f"/v2/sql/instance/{instance_id}/history/backup")
            
            if not jobs:
                logger.debug(f"No SQL jobs found for instance: {instance_id}")
                return

            for job in jobs:
                try:
                    job_id = str(job.get('jobId', 'unknown'))
                    status = job.get('status', 'unknown').lower()
                    job_type = job.get('jobType', 'unknown').lower()
                    db_name = job.get('databaseName', 'unknown')
                    duration = float(jog.get('duration', 0))

                    status_value = 1 if status == 'completed' else 0
                    self.sql_job_status.add_metric(
                        [job_id, instance_id, db_name, status, job_type],
                        status_value
                    )
                    self.sql_job_duration.add_metric(
                        [job_id, instance_id, db_name, job_type],
                        duration
                    )
                    logger.debug(f"Processed SQL job {job_id} for DB {db_name}")
                except (KeyError, ValueError) as e:
                    logger.warning(f"Skipping malformed SQL job entry: {str(e)}")
                    continue

            logger.info(f"Successfully collected {len(jobs)} SQL jobs for instance: {instance_id}")
        except Exception as e:
            logger.error(f"SQL job collection failed for instance {instance_id}: {str(e)}")
            raise

    def collect(self):
        """Collect Prometheus metrics"""
        start_time = time.time()
        success = 0
        metrics = []
        
        try:
            logger.info("Starting metrics collection")
            
            # Collect system info (runs in main thread)
            self._collect_system_info()
            metrics.append(self.system_info)
            
            # Create thread pool for concurrent collection
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = {
                    executor.submit(self._collect_vsa_jobs): 'VSA jobs',
                    executor.submit(self._collect_sql_jobs): 'SQL jobs'
                }
                
                for future in concurrent.futures.as_completed(futures):
                    task_name = futures[future]
                    try:
                        future.result()
                        logger.debug(f"{task_name} collection completed successfully")
                    except Exception as e:
                        logger.error(f"{task_name} collection failed: {str(e)}")
                        success = 0  # Mark as failed if any collection fails
            
            # Add all metrics after collection is complete
            metrics.extend([
                self.vsa_job_status,
                self.vsa_job_duration,
                self.sql_job_status,
                self.sql_job_duration,
                self.scrape_success,
                self.scrape_duration
            ])
            
            # Mark as successful if we got this far
            success = 1
            logger.info("Metrics collection completed successfully")
            
            return metrics
            
        except Exception as e:
            logger.error(f"Metrics collection failed: {str(e)}")
            success = 0
            # Return basic metrics even on failure
            return [
                self.scrape_success,
                self.scrape_duration
            ]
            
        finally:
            duration = time.time() - start_time
            self.scrape_duration.add_metric([], duration)
            self.scrape_success.add_metric([], success)
            logger.info(f"Scrape completed in {duration:.2f} seconds (success: {success})")

def start_exporter(config: ConfigHandler):
    """Start the Prometheus exporter"""
    try:
        logger.debug(f"start_exporter received config type: {type(config)}")
        if not isinstance(config, ConfigHandler):
            raise ValueError(f"Expected ConfigHandler, got {type(config)}")
            
        logger.info("Starting Commvault exporter")
        collector = CommvaultCollector(config)
        REGISTRY.register(collector)
        port = config.get('exporter', 'port', default=9657)
        start_http_server(port)
        logger.info(f"Exporter started on port {port}")
    except Exception as e:
        logger.error(f"Failed to start exporter: {str(e)}")
        raise