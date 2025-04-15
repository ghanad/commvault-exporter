# Commvault Prometheus Exporter

A Prometheus exporter for Commvault backup metrics that collects and exposes backup job information and system health metrics.

## Features

- Collects metrics from Commvault API
- Exposes metrics in Prometheus format
- Supports both VSA (Virtual Server Agent) and SQL backup jobs
- Configurable through YAML file and environment variables

## Configuration

Create `config/config.yaml` with the following structure:

```yaml
commvault:
  api_url: "https://your-commvault-server/webconsole/api"
  username: "api_user"
  password: "api_password"
  version: "11.0"  # Commvault version
  commserve_name: "your_commserve"  # CommServe server name
  vm_guid: "vm-guid-here"  # For VSA job collection
  sql_instance_id: "sql-instance-id"  # For SQL job collection
exporter:
  port: 9657  # Metrics port
  log_level: "INFO"  # DEBUG, INFO, WARNING, ERROR
  timeout: 30  # API timeout in seconds
```

Environment variables can override any config value by prefixing with `COMMVAULT_` or `EXPORTER_` (e.g., `EXPORTER_PORT=9658`).

## Prometheus Configuration

Add this to your `prometheus.yml` to scrape the exporter:

```yaml
scrape_configs:
  - job_name: 'commvault'
    static_configs:
      - targets: ['exporter-host:9657']
        labels:
          environment: 'production'
          commvault_server: 'your-commserve'
```

## Installation

### Python Environment

1. Clone the repository
2. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac)
   venv\Scripts\activate  # Windows
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Docker

```bash
docker build -t commvault-exporter .
docker run -p 9657:9657 commvault-exporter
```

## Running

```bash
python run.py
```

Or using the installed package:
```bash
commvault-exporter
```

## Exposed Metrics

### System Metrics
- `commvault_info`: Commvault system information
- `commvault_scrape_duration_seconds`: Scrape duration
- `commvault_scrape_success`: Scrape success status

### VSA Job Metrics
- `commvault_vsa_job_status`: Job status (1=success, 0=failure)
- `commvault_vsa_job_duration_seconds`: Job duration

### SQL Job Metrics
- `commvault_sql_job_status`: Job status (1=success, 0=failure)
- `commvault_sql_job_duration_seconds`: Job duration

## Troubleshooting

### Common Issues

1. **Authentication failures**:
   - Verify API credentials
   - Check Commvault API URL

2. **No metrics appearing**:
   - Check exporter logs for errors
   - Verify VM GUID/SQL instance ID are correct
   - Ensure Commvault user has proper permissions

3. **Connection issues**:
   - Verify network connectivity to Commvault server
   - Check firewall settings

### Logs

Logs are in JSON format and can be filtered by level:
```bash
grep '"level": "ERROR"' exporter.log
```

## License

MIT License - See [LICENSE](LICENSE) for details.