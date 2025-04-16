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
        self.api_client = CommvaultAPIClient(config)
        self._skip_first_collect = True
        
        # Essential metrics (must always be available)
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

        # Old metrics (deprecated but still required)
        self.vm_client_status = GaugeMetricFamily(
            'commvault_vm_client_status',
            'Status of VM Pseudo Clients',
            labels=['client_id', 'client_name', 'host_name', 'instance_name', 'status']
        )
        
        self.vm_client_activity = GaugeMetricFamily(
            'commvault_vm_client_activity_control',
            'Activity control status for VM Pseudo Clients',
            labels=['client_id', 'client_name', 'activity_type', 'enabled']
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

        # New job metrics
        self.job_status = GaugeMetricFamily(
            'commvault_job_status',
            'Gauge tracking job status (Completed=1, Failed=0, Running=2)',
            labels=['jobId', 'jobType', 'clientName', 'subclientName']
        )

        self.job_duration = GaugeMetricFamily(
            'commvault_job_duration_seconds',
            'Gauge measuring job duration in seconds',
            labels=['jobId', 'jobType', 'clientName']
        )

        self.job_start_time = GaugeMetricFamily(
            'commvault_job_start_time',
            'Gauge for job start time (Unix timestamp)',
            labels=['jobId', 'jobType']
        )

        self.job_end_time = GaugeMetricFamily(
            'commvault_job_end_time',
            'Gauge for job end time (Unix timestamp)',
            labels=['jobId', 'jobType']
        )

        self.job_failed_files = GaugeMetricFamily(
            'commvault_job_failed_files',
            'Counter for the number of failed files in a job',
            labels=['jobId', 'jobType']
        )

        self.job_failed_folders = GaugeMetricFamily(
            'commvault_job_failed_folders',
            'Counter for the number of failed folders in a job',
            labels=['jobId', 'jobType']
        )

        self.job_percent_complete = GaugeMetricFamily(
            'commvault_job_percent_complete',
            'Gauge for job completion percentage (0-100)',
            labels=['jobId', 'jobType']
        )

        self.job_size_application_bytes = GaugeMetricFamily(
            'commvault_job_size_application_bytes',
            'Gauge for the size of the application data processed (bytes)',
            labels=['jobId', 'jobType']
        )

        self.job_size_media_bytes = GaugeMetricFamily(
            'commvault_job_size_media_bytes',
            'Gauge for the size of media on disk (bytes)',
            labels=['jobId', 'jobType']
        )

        self.job_alert_level = GaugeMetricFamily(
            'commvault_job_alert_level',
            'Gauge for alert severity (0=normal, higher=issues)',
            labels=['jobId', 'jobType']
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


    def _collect_vm_pseudo_clients(self) -> None:
        """Collect metrics for VM Pseudo Clients"""
        try:
            endpoint = "/Client/VMPseudoClient"
            full_url = self.api_client.get_full_url(endpoint)
            logger.info(f"Making API request to: {full_url}")
            response = self.api_client.get(endpoint)
            
            if not response or 'VSPseudoClientsList' not in response:
                logger.debug("No VM Pseudo Clients found in response")
                return
                
            for client in response['VSPseudoClientsList']:
                try:
                    # Extract client info
                    client_id = str(client.get('client', {}).get('clientId', 'unknown'))
                    client_name = client.get('client', {}).get('clientName', 'unknown')
                    host_name = client.get('client', {}).get('hostName', 'unknown')
                    instance_name = client.get('instance', {}).get('instanceName', 'unknown')
                    status = str(client.get('status', 'unknown'))
                    
                    # Add status metric
                    status_value = 1 if status == '0' else 0  # 0 means active in Commvault
                    self.vm_client_status.add_metric(
                        [client_id, client_name, host_name, instance_name, status],
                        status_value
                    )
                    
                    # Add activity control metrics
                    for activity in client.get('clientActivityControl', {}).get('activityControlOptions', []):
                        activity_type = str(activity.get('activityType', 'unknown'))
                        enabled = 1 if activity.get('enableActivityType', False) else 0
                        self.vm_client_activity.add_metric(
                            [client_id, client_name, activity_type, str(enabled)],
                            enabled
                        )
                        
                    logger.debug(f"Processed VM Pseudo Client {client_name} (ID: {client_id})")
                except (KeyError, ValueError) as e:
                    logger.warning(f"Skipping malformed VM Pseudo Client entry: {str(e)}")
                    continue
                    
            logger.info(f"Successfully collected {len(response['VSPseudoClientsList'])} VM Pseudo Clients")
        except Exception as e:
            logger.error(f"VM Pseudo Client collection failed: {str(e)}")
            raise

    def _collect_job_metrics(self) -> None:
        """Collect metrics for Commvault jobs"""
        try:
            endpoint = "/Job"
            full_url = self.api_client.get_full_url(endpoint)
            logger.info(f"Making API request to: {full_url}")
            jobs = self.api_client.get(endpoint)
            
            if not jobs or 'jobs' not in jobs:
                logger.debug("No jobs found in response")
                return
                
            for job in jobs['jobs']:
                try:
                    job_id = str(job.get('jobSummary', {}).get('jobId', 'unknown'))
                    job_type = job.get('jobSummary', {}).get('jobType', 'unknown').lower()
                    client_name = job.get('jobSummary', {}).get('subclient', {}).get('clientName', 'unknown')
                    subclient_name = job.get('jobSummary', {}).get('subclientName', 'unknown')
                    status = job.get('jobSummary', {}).get('status', 'unknown').lower()
                    duration = float(job.get('jobSummary', {}).get('jobElapsedTime', 0))
                    start_time = float(job.get('jobSummary', {}).get('jobStartTime', 0))
                    end_time = float(job.get('jobSummary', {}).get('jobEndTime', 0))
                    failed_files = int(job.get('jobSummary', {}).get('totalFailedFiles', 0))
                    failed_folders = int(job.get('jobSummary', {}).get('totalFailedFolders', 0))
                    percent_complete = float(job.get('jobSummary', {}).get('percentComplete', 0))
                    app_size = float(job.get('jobSummary', {}).get('sizeOfApplication', 0))
                    media_size = float(job.get('jobSummary', {}).get('sizeOfMediaOnDisk', 0))
                    alert_level = int(job.get('jobSummary', {}).get('alertColorLevel', 0))

                    # Set status value (Completed=1, Failed=0, Running=2)
                    status_value = 1 if status == 'completed' else (2 if status == 'running' else 0)
                    
                    # Add all metrics for this job
                    self.job_status.add_metric([job_id, job_type, client_name, subclient_name], status_value)
                    self.job_duration.add_metric([job_id, job_type, client_name], duration)
                    self.job_start_time.add_metric([job_id, job_type], start_time)
                    self.job_end_time.add_metric([job_id, job_type], end_time)
                    self.job_failed_files.add_metric([job_id, job_type], failed_files)
                    self.job_failed_folders.add_metric([job_id, job_type], failed_folders)
                    self.job_percent_complete.add_metric([job_id, job_type], percent_complete)
                    self.job_size_application_bytes.add_metric([job_id, job_type], app_size)
                    self.job_size_media_bytes.add_metric([job_id, job_type], media_size)
                    self.job_alert_level.add_metric([job_id, job_type], alert_level)
                    
                    logger.debug(f"Processed job {job_id} with status {status}")
                except (KeyError, ValueError) as e:
                    logger.warning(f"Skipping malformed job entry: {str(e)}")
                    continue
                    
            logger.info(f"Successfully collected {len(jobs['jobs'])} jobs")
        except Exception as e:
            logger.error(f"Job metrics collection failed: {str(e)}")
            raise

    def collect(self):
        """Collect Prometheus metrics"""
        if self._skip_first_collect:
            self._skip_first_collect = False
            return []
            
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
                        # executor.submit(self._collect_vsa_jobs): 'VSA jobs',
                        # executor.submit(self._collect_sql_jobs): 'SQL jobs',
                        executor.submit(self._collect_vm_pseudo_clients): 'VM Pseudo Clients',
                        executor.submit(self._collect_job_metrics): 'Job metrics'
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
                # self.sql_job_status,
                # self.sql_job_duration,
                self.vm_client_status,
                self.vm_client_activity,
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

    def _test_endpoints(self) -> None:
        """
        روش استفاده از این تابع موقت:
        1. لیست endpoint های مورد نظر خود را در آرایه زیر اضافه کنید
        2. exporter را به صورت معمولی اجرا کنید
        3. خروجی را در فایل لاگ بررسی کنید
        4. بعد از اتمام تست، این تابع را حذف کنید
        
        مثال endpoint ها:
        """
        endpoints_to_test = [
            # "/Client/VMPseudoClient",  # مثال: دریافت لیست مشتریان مجازی
            # "/Client",
            # "/StoragePolicy",
            # "/MediaAgent",
            # "/VM",
            # "/Job",
            # "/Alert",
            # "/CommServ/Health", # Not exists
            # "/Client",
        ]
        
        for endpoint in endpoints_to_test:
            try:
                logger.info(f"tesing endpoint: {endpoint}")
                response = self.api_client.get(endpoint)
                logger.info(f"response {endpoint}: {str(response)[:200]}...") 
            except Exception as e:
                logger.error(f"error endpoint {endpoint}: {str(e)}")
        logger.info("end")

def start_exporter(config: ConfigHandler):
    """Start the Prometheus exporter"""
    try:
        logger.debug(f"start_exporter received config type: {type(config)}")
        if not isinstance(config, ConfigHandler):
            raise ValueError(f"Expected ConfigHandler, got {type(config)}")
            
        logger.info("Starting Commvault exporter")
        collector = CommvaultCollector(config)
        
        port = config.get('exporter', 'port', default=9657)
        start_http_server(port)
        REGISTRY.register(collector)
        logger.info(f"Exporter started on port {port}")
    except Exception as e:
        logger.error(f"Failed to start exporter: {str(e)}")
        raise