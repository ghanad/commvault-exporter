# Commvault Prometheus Exporter

A Prometheus exporter for Commvault environments that collects metrics via the Commvault REST API using a multi-target probe mechanism.

## Features

-   Collects metrics from multiple Commvault targets using a single exporter instance running on **one port**.
-   Uses the `/probe` endpoint pattern, similar to `blackbox_exporter`.
-   Fetches Job Status, VM Client Status, System Info, and potentially other metrics (configurable/extendable).
-   Exposes metrics in Prometheus format.
-   Configuration via YAML file and limited environment variables.

## Configuration

Create `config/config.yaml` with the following structure to define your Commvault targets and exporter settings:

```yaml
# Define the Commvault instances you want to monitor
targets:
  # Use descriptive names for your targets (these are used in the ?target= URL parameter)
  prod-commserve:
    api_url: "https://prod-commserve.example.com/webconsole/api"
    username: "prom_user_prod"
    password: "prod_password"
    # Optional: Specify Commvault version (used for 'commvault_info' metric)
    version: "11.28"
    # Optional: Specify a friendly name for the commserve (used for 'commvault_info' metric)
    commserve_name: "Production Commserve"
    # Optional: Override global SSL verification (default: true)
    verify_ssl: true
    # Optional: Override global timeout per target (default: 30 seconds)
    # timeout: 60

  dev-commserve:
    api_url: "https://dev-commserve.example.com/webconsole/api"
    username: "prom_user_dev"
    password: "dev_password"
    version: "11.24"
    commserve_name: "Development Commserve"
    # Example: Disable SSL verification for a specific target (e.g., self-signed cert)
    verify_ssl: false

  # Add more targets as needed...
  # target-name-3:
  #   api_url: "..."
  #   username: "..."
  #   password: "..."

# Global exporter settings
exporter:
  # Port the exporter listens on for ALL requests (only /probe is served)
  port: 9658 # Default if not specified
  # API request timeout in seconds (can be overridden per target)
  timeout: 30 # Default if not specified
  # Logging configuration
  log_level: "INFO" # DEBUG, INFO, WARNING, ERROR, CRITICAL
  logging:
    # Optional: Log to a file
    file: "logs/commvault_exporter.log" # Path relative to where exporter runs
    # Optional: Max log file size in MB before rotation
    max_size: 10
    # Optional: Number of backup log files to keep
    backup_count: 5