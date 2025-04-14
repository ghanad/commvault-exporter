import base64
import requests
from typing import Optional
from datetime import datetime, timedelta
from ..config_handler import ConfigHandler

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
            raise Exception(f"Login failed: {str(e)}") from e

    def _is_token_valid(self) -> bool:
        """Check if current token is valid and not expired"""
        return self.auth_token and self.token_expiry and self.token_expiry > datetime.now()

    def get_auth_token(self) -> str:
        """Get current auth token, logging in if needed or token expired"""
        if not self._is_token_valid():
            self.login()
        return self.auth_token

    def refresh_token(self) -> str:
        """Force refresh of auth token"""
        return self.login()