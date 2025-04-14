import base64
import requests
from typing import Optional
from ..config_handler import ConfigHandler

class CommvaultAPIClient:
    def __init__(self, config: ConfigHandler):
        self.config = config
        self.auth_token: Optional[str] = None
        self.api_url = self.config.get('commvault', 'api_url')
        self.username = self.config.get('commvault', 'username')
        self.password = self.config.get('commvault', 'password')

    def login(self) -> Optional[str]:
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
            return self.auth_token

        except requests.exceptions.RequestException as e:
            raise Exception(f"Login failed: {str(e)}") from e

    def get_auth_token(self) -> str:
        """Get current auth token, logging in if needed"""
        if not self.auth_token:
            self.login()
        return self.auth_token