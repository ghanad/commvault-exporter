from flask import Flask, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from .config_handler import ConfigHandler
from .logger import setup_logging

app = Flask(__name__)
config = ConfigHandler()
setup_logging(config)

@app.route('/metrics')
def metrics():
    """Expose Prometheus metrics"""
    return Response(
        generate_latest(),
        mimetype=CONTENT_TYPE_LATEST
    )

@app.route('/health')
def health():
    """Health check endpoint"""
    return 'OK', 200

def run():
    app.run(
        host='0.0.0.0',
        port=config.get('exporter', 'port'),
        debug=(config.get('exporter', 'log_level') == 'DEBUG')
    )

if __name__ == '__main__':
    run()