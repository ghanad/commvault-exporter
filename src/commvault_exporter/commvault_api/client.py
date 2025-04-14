import base64
import requests
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from urllib.parse import urljoin
from ..config_handler import ConfigHandler

logger = logging.getLogger(__name__)

class CommvaultAPIClient:
    def __init__(self, config: ConfigHandler):
        self.config = config
        self.auth_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self.api_url = self.config.get('commvault', 'api_url')
        self.username = self.config.get('commvault', 'username')
        self.password = self.config.get('commvault', 'password')

    def login(self) -> str:
        """Authenticate with Commvault API and store auth token"""
        if not all([self.api_url, self.username, self.password]):
            raise ValueError("Missing required configuration for API login")

        try:
            # Base64 encode the password
            encoded_pwd = base64.b64encode(self.password.encode()).decode()

            response = requests.post(
                f"{self.api_url}/Login",
                json={
                    "username": self.username,
                    "password": encoded_pwd
                },
                timeout=self.config.get('exporter', 'timeout')
            )
            response.raise_for_status()

            data = response.json()
            self.auth_token = data.get('token')
            
            # Set token expiry (default 1 hour if not provided)
            expires_in = data.get('expires_in', 3600)
            self.token_expiry = datetime.now() + timedelta(seconds=expires_in)
            
            return self.auth_token

        except requests.exceptions.RequestException as e:
            logger.error(f"Login failed: {str(e)}")
            raise Exception(f"Login failed: {str(e)}") from e

    def _is_token_valid(self) -> bool:
        """Check if current token is valid and not expired"""
        return self.auth_token and self.token_expiry and self.token_expiry > datetime.now()

    def get_auth_token(self) -> str:
        """Get current auth token, logging in if needed or token expired"""
        if not self._is_token_valid():
            self.login()
        return self.auth_token

    def get(self, endpoint: str, params: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        Make a GET request to the Commvault API
        Args:
            endpoint: API endpoint path (e.g. '/v2/vsa/vm/jobs')
            params: Optional query parameters
        Returns:
            Parsed JSON response or None on error
        """
        try:
            # Ensure we have a valid token
            token = self.get_auth_token()
            
            # Construct full URL
            url = urljoin(self.api_url, endpoint)
            
            # Prepare headers
            headers = {
                'Authtoken': token,
                'Accept': 'application/json'
            }
            
            logger.debug(f"Making GET request to {url} with params {params}")
            
            # Make the request
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=self.config.get('exporter', 'timeout')
            )
            
            # Check for errors
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed to {endpoint}: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}, content: {e.response.text}")
            return None