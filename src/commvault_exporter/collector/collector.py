from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily, REGISTRY, CollectorRegistry
# Import generate_latest function AND the CONTENT_TYPE_LATEST constant
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from typing import List, Dict, Any, Optional, Iterable
import time
import logging
import concurrent.futures
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import functools
import threading
import sys # For sys.exit

# Import necessary classes (adjust paths if needed)
from ..commvault_api.client import CommvaultAPIClient
from ..config_handler import ConfigHandler

logger = logging.getLogger(__name__)

# --- Metric Definitions Helper ---
def add_target_label(metric_family_class, name, documentation, labels):
    """Helper to add 'commvault_target' to the labels list."""
    if 'commvault_target' not in labels:
        labels.append('commvault_target')
    return metric_family_class(name, documentation, labels=labels)

# --- CommvaultCollector Class ---
class CommvaultCollector:
    """
    Collects metrics for a specific Commvault target.
    An instance of this collector is created per probe request.
    """
    def __init__(self, target_name: str, target_config: Dict[str, Any]):
        """
        Initializes the collector for a specific target.

        Args:
            target_name: The name of the target (used as label value).
            target_config: The configuration dictionary for this target.
        """
        logger.debug(f"Initializing collector for target: {target_name}")
        if not target_config:
             raise ValueError(f"Target configuration for '{target_name}' is missing or empty.")

        self.target_name = target_name
        self.target_config = target_config
        self.api_client: Optional[CommvaultAPIClient] = None # Client is initialized separately

        # --- Define Metrics ---
        self.scrape_duration = add_target_label(
            GaugeMetricFamily, 'commvault_scrape_duration_seconds',
            'Time the Commvault scrape took for this target', []
        )
        self.scrape_success = add_target_label(
            GaugeMetricFamily, 'commvault_scrape_success',
            'Whether the Commvault scrape succeeded for this target (1 for success, 0 for failure)', []
        )
        self.system_info = add_target_label(
            GaugeMetricFamily, 'commvault_info',
            'Commvault system information for this target', ['version', 'commserve_name']
        )
        self.vm_client_status = add_target_label(
            GaugeMetricFamily, 'commvault_vm_client_status',
            'Status of VM Pseudo Clients', ['client_id', 'client_name', 'host_name', 'instance_name', 'status']
        )
        self.vm_client_activity = add_target_label(
            GaugeMetricFamily, 'commvault_vm_client_activity_control',
            'Activity control status for VM Pseudo Clients', ['client_id', 'client_name', 'activity_type', 'enabled']
        )
        self.job_status = add_target_label(
            GaugeMetricFamily, 'commvault_job_status',
            'Gauge tracking job status (Completed=1, Failed=0, Running=2, Other=3)',
            ['jobId', 'jobType', 'clientName', 'subclientName']
        )
        self.job_duration = add_target_label(
            GaugeMetricFamily, 'commvault_job_duration_seconds',
            'Gauge measuring job duration in seconds',
            ['jobId', 'jobType', 'clientName']
        )
        self.job_start_time = add_target_label(
            GaugeMetricFamily, 'commvault_job_start_time_seconds',
            'Gauge for job start time (Unix timestamp)',
            ['jobId', 'jobType']
        )
        self.job_end_time = add_target_label(
            GaugeMetricFamily, 'commvault_job_end_time_seconds',
            'Gauge for job end time (Unix timestamp)',
            ['jobId', 'jobType']
        )
        self.job_failed_files = add_target_label(
            GaugeMetricFamily, 'commvault_job_failed_files_total',
            'Gauge for the number of failed files in the last job run', # Changed doc slightly
            ['jobId', 'jobType']
        )
        self.job_failed_folders = add_target_label(
            GaugeMetricFamily, 'commvault_job_failed_folders_total',
            'Gauge for the number of failed folders in the last job run', # Changed doc slightly
            ['jobId', 'jobType']
        )
        self.job_percent_complete = add_target_label(
            GaugeMetricFamily, 'commvault_job_percent_complete',
            'Gauge for job completion percentage (0-100)',
            ['jobId', 'jobType']
        )
        self.job_size_application_bytes = add_target_label(
            GaugeMetricFamily, 'commvault_job_size_application_bytes',
            'Gauge for the size of the application data processed (bytes)',
            ['jobId', 'jobType']
        )
        self.job_size_media_bytes = add_target_label(
            GaugeMetricFamily, 'commvault_job_size_media_bytes',
            'Gauge for the size of media on disk (bytes)',
            ['jobId', 'jobType']
        )
        self.job_alert_level = add_target_label(
            GaugeMetricFamily, 'commvault_job_alert_level',
            'Gauge for alert severity (0=normal, higher=issues)',
            ['jobId', 'jobType']
        )

    def initialize_client(self) -> None:
        """Instantiates the API client for this collector instance."""
        if not self.api_client:
            logger.debug(f"Creating API client for target {self.target_name}")
            try:
                self.api_client = CommvaultAPIClient(self.target_config)
                logger.info(f"API client initialized successfully for target {self.target_name}")
            except Exception as e:
                logger.error(f"Failed to initialize API client for target {self.target_name}: {e}")
                self.api_client = None
                raise

    def _add_metric_with_target(self, metric_family, labels: List[str], value: float):
        """Helper to add the target name as the last label value."""
        metric_family.add_metric(labels + [self.target_name], value)

    # --- Data Collection Methods ---
    def _collect_system_info(self) -> None:
        if not self.api_client: return
        try:
            version = self.target_config.get('version', 'unknown')
            commserve_name = self.target_config.get('commserve_name', self.target_name)
            self._add_metric_with_target(self.system_info, [version, commserve_name], 1)
            logger.debug(f"[{self.target_name}] Collected system info - Version: {version}, Server: {commserve_name}")
        except Exception as e:
            logger.error(f"[{self.target_name}] Failed to collect system info: {str(e)}")

    def _collect_vm_pseudo_clients(self) -> None:
        if not self.api_client: return
        try:
            endpoint_to_try = "/Client/VMPseudoClient"
            logger.info(f"[{self.target_name}] Making API request to: {endpoint_to_try}")
            response = self.api_client.get(endpoint_to_try)
            if not response or 'VSPseudoClientsList' not in response:
                 logger.debug(f"[{self.target_name}] No 'VSPseudoClientsList' found in response from {endpoint_to_try}.")
                 return
            count = 0
            for client in response.get('VSPseudoClientsList', []):
                try:
                    client_entity = client.get('client', {}).get('clientEntity', client.get('client', {}))
                    client_id = str(client_entity.get('clientId', 'unknown'))
                    client_name = client_entity.get('clientName', 'unknown')
                    host_name = client_entity.get('hostName', 'unknown')
                    instance_name = client.get('instance', {}).get('instanceName', 'unknown')
                    status_code = str(client.get('statusInfo', {}).get('status', client.get('status', 'unknown')))
                    status_str = client.get('statusInfo', {}).get('statusString', status_code)
                    status_value = 1 if status_code in ['0', '1'] or status_str.lower() == 'configured' else 0
                    self._add_metric_with_target(
                        self.vm_client_status, [client_id, client_name, host_name, instance_name, status_str], status_value
                    )
                    for activity in client.get('clientActivityControl', {}).get('activityControlOptions', []):
                        activity_type = str(activity.get('activityType', 'unknown'))
                        enabled = 1 if activity.get('enableActivityType', False) else 0
                        self._add_metric_with_target(
                            self.vm_client_activity, [client_id, client_name, activity_type, str(enabled)], enabled
                        )
                    count += 1
                except (AttributeError, KeyError, ValueError, TypeError) as e:
                    logger.warning(f"[{self.target_name}] Skipping malformed VM Pseudo Client entry: {e}. Data: {str(client)[:200]}")
            logger.info(f"[{self.target_name}] Successfully processed {count} VM Pseudo Clients")
        except Exception as e:
            logger.error(f"[{self.target_name}] VM Pseudo Client collection failed: {str(e)}")

    def _collect_job_metrics(self) -> None:
        if not self.api_client: return
        try:
            endpoint = "/Job"
            params = {'completed': 'true', 'lookupFinishedJobs': 'true', 'allProps': 'true', 'limit': 1000} # Added limit
            logger.info(f"[{self.target_name}] Making API request to: {endpoint} with params: {params}")
            response = self.api_client.get(endpoint, params=params)
            if not response or 'jobs' not in response:
                logger.debug(f"[{self.target_name}] No 'jobs' key found in response from {endpoint}.")
                return
            count = 0
            for job in response.get('jobs', []):
                try:
                    summary = job.get('jobSummary', {})
                    if not summary: continue
                    job_id = str(summary.get('jobId', 'unknown'))
                    job_type = summary.get('jobType', 'unknown').replace(" ", "_").lower()
                    client_entity = summary.get('clientEntity', summary.get('client', {}))
                    client_name = client_entity.get('clientName', 'unknown')
                    subclient_info = summary.get('subclient', {})
                    subclient_name = subclient_info.get('subclientName', 'unknown')
                    status = summary.get('status', 'unknown').lower()
                    duration = float(summary.get('jobElapsedTime', 0))
                    start_time = float(summary.get('jobStartTime', 0))
                    end_time = float(summary.get('jobEndTime', 0))
                    failed_files = int(summary.get('totalFailedFiles', 0))
                    failed_folders = int(summary.get('totalFailedFolders', 0))
                    percent_complete = float(summary.get('percentComplete', 0))
                    app_size = float(summary.get('sizeOfApplication', 0))
                    media_size = float(summary.get('sizeOfMediaOnDisk', 0))
                    alert_level = int(summary.get('alertColorLevel', summary.get('severity', 0)))

                    if status in ['completed']: status_value = 1
                    elif status in ['running', 'waiting', 'pending', 'queued', 'suspended']: status_value = 2
                    elif status in ['failed', 'killed', 'completed w/ errors', 'completed w/ warnings', 'no run']: status_value = 0
                    else: status_value = 3

                    labels_status = [job_id, job_type, client_name, subclient_name]
                    self._add_metric_with_target(self.job_status, labels_status, status_value)
                    labels_duration = [job_id, job_type, client_name]
                    self._add_metric_with_target(self.job_duration, labels_duration, duration)
                    labels_common = [job_id, job_type]
                    self._add_metric_with_target(self.job_start_time, labels_common, start_time)
                    self._add_metric_with_target(self.job_end_time, labels_common, end_time)
                    self._add_metric_with_target(self.job_failed_files, labels_common, failed_files)
                    self._add_metric_with_target(self.job_failed_folders, labels_common, failed_folders)
                    self._add_metric_with_target(self.job_percent_complete, labels_common, percent_complete)
                    self._add_metric_with_target(self.job_size_application_bytes, labels_common, app_size)
                    self._add_metric_with_target(self.job_size_media_bytes, labels_common, media_size)
                    self._add_metric_with_target(self.job_alert_level, labels_common, alert_level)
                    count += 1
                except (AttributeError, KeyError, ValueError, TypeError) as e:
                    logger.warning(f"[{self.target_name}] Skipping malformed job entry: {e}. Data: {str(job)[:200]}")
            logger.info(f"[{self.target_name}] Successfully processed {count} jobs from {endpoint}")
        except Exception as e:
            logger.error(f"[{self.target_name}] Job metrics collection failed: {str(e)}")

    def collect(self) -> Iterable[GaugeMetricFamily]:
        """
        Collects all metrics for the target. Called by Prometheus client library.
        Orchestrates calls to the specific _collect_* methods.
        """
        if not self.api_client:
            logger.error(f"[{self.target_name}] Collect called but API client is not initialized.")
            self._add_metric_with_target(self.scrape_success, [], 0)
            self._add_metric_with_target(self.scrape_duration, [], 0)
            yield self.scrape_success
            yield self.scrape_duration
            return

        start_time = time.time()
        overall_success = True
        logger.info(f"[{self.target_name}] Starting metrics collection")

        collection_tasks = {
            self._collect_system_info: "System Info",
            self._collect_vm_pseudo_clients: "VM Pseudo Clients",
            self._collect_job_metrics: "Job Metrics",
        }

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                 future_to_task = {executor.submit(task): name for task, name in collection_tasks.items()}
                 for future in concurrent.futures.as_completed(future_to_task):
                     task_name = future_to_task[future]
                     try:
                         future.result()
                         logger.debug(f"[{self.target_name}] Task '{task_name}' completed successfully.")
                     except Exception as exc:
                         logger.error(f"[{self.target_name}] Task '{task_name}' failed: {exc}")
                         overall_success = False
        except Exception as e:
             logger.error(f"[{self.target_name}] Error during concurrent collection execution: {e}")
             overall_success = False

        duration = time.time() - start_time
        self._add_metric_with_target(self.scrape_duration, [], duration)
        self._add_metric_with_target(self.scrape_success, [], 1 if overall_success else 0)
        logger.info(f"[{self.target_name}] Scrape completed in {duration:.2f} seconds (success: {overall_success})")

        # Yield all metrics that were populated
        yield self.scrape_duration
        yield self.scrape_success
        yield self.system_info
        yield self.vm_client_status
        yield self.vm_client_activity
        yield self.job_status
        yield self.job_duration
        yield self.job_start_time
        yield self.job_end_time
        yield self.job_failed_files
        yield self.job_failed_folders
        yield self.job_percent_complete
        yield self.job_size_application_bytes
        yield self.job_size_media_bytes
        yield self.job_alert_level


# --- Probe HTTP Handler ---
class ProbeHandler(BaseHTTPRequestHandler):
    """
    Handles HTTP requests to the /probe endpoint.
    Creates a temporary collector for the specific target requested.
    """
    def __init__(self, config: ConfigHandler, *args, **kwargs):
        """
        Initializes the handler with the global configuration.
        'config' is passed via functools.partial during server setup.
        """
        self.config = config
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Handles GET requests."""
        url = urlparse(self.path)
        if url.path != '/probe':
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Not Found: Use the /probe?target=... endpoint")
            return

        query_params = parse_qs(url.query)
        target_list = query_params.get('target', [])

        if not target_list:
            logger.error("Probe request missing 'target' parameter")
            self.send_response(400)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Bad Request: 'target' parameter is required")
            return

        target_name = target_list[0]
        logger.info(f"Received probe request for target: {target_name}")

        target_config = self.config.get_target_config(target_name)

        if not target_config:
            logger.error(f"Target '{target_name}' not found in configuration")
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(f"Target '{target_name}' not found in configuration".encode('utf-8'))
            return

        registry = CollectorRegistry()
        collector = None

        try:
            collector = CommvaultCollector(target_name, target_config)
            collector.initialize_client()
            registry.register(collector)

            # Generate metrics using the temporary registry and collector instance
            output = generate_latest(registry)

            # Send success response
            self.send_response(200)
            # Use the directly imported constant here
            self.send_header('Content-Type', CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(output)
            logger.info(f"Successfully processed probe for target: {target_name}")

        except Exception as e:
            error_message = f"Failed to probe target '{target_name}': {str(e)}"
            logger.exception(error_message) # Log full traceback for debugging
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(error_message.encode('utf-8'))


# --- Exporter Start Function ---

def start_http_server(config: ConfigHandler):
    """Starts the single HTTP server for the /probe endpoint."""
    port = config.get_exporter_port()
    logger.info(f"Starting exporter HTTP server on port {port} for /probe endpoint")

    handler = functools.partial(ProbeHandler, config)
    server = None
    try:
        server = HTTPServer(('', port), handler)
        server.serve_forever()
    except OSError as e:
        logger.error(f"Failed to start HTTP server on port {port}: {e} - Is the port already in use?")
        sys.exit(f"Port {port} already in use.")
    except KeyboardInterrupt:
        logger.info("Exporter server received shutdown signal.")
        if server:
             server.shutdown()
        logger.info("Exporter server stopped.")
    except Exception as e:
        logger.error(f"Exporter HTTP server failed unexpectedly: {e}", exc_info=True)
        if server:
            server.shutdown()
        raise


def start_exporter(config: ConfigHandler):
    """
    Initializes and starts the exporter's HTTP server.
    """
    if not isinstance(config, ConfigHandler):
        raise ValueError(f"start_exporter requires a ConfigHandler instance, got {type(config)}")

    if not config.get_all_targets():
        logger.warning("No targets defined in configuration. Server will start but /probe requests will fail to find targets.")

    start_http_server(config)