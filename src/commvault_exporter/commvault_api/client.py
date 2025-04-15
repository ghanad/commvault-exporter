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
            error_msg = "Missing required configuration for API login"
            logger.error(error_msg)
            raise ValueError(error_msg)

        try:
            # Base64 encode the password
            encoded_pwd = base64.b64encode(self.password.encode()).decode()

            logger.debug(f"Attempting login to {self.api_url} as {self.username}")
            response = requests.post(
                f"{self.api_url}/Login",
                json={
                    "username": self.username,
                    "password": encoded_pwd
                },
                timeout=self.config.get('exporter', 'timeout')
            )
            
            # Check for HTTP errors
            response.raise_for_status()
            data = response.json()

            if not data.get('token'):
                error_msg = "Login response missing auth token"
                logger.error(error_msg)
                raise ValueError(error_msg)

            self.auth_token = data['token']
            expires_in = data.get('expires_in', 3600)
            self.token_expiry = datetime.now() + timedelta(seconds=expires_in)
            
            logger.info("Login successful")
            return self.auth_token

        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP error during login: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            raise Exception(error_msg) from e
        except requests.exceptions.RequestException as e:
            error_msg = f"Request failed during login: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e
        except (ValueError, KeyError) as e:
            error_msg = f"Invalid response format during login: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

    def _is_token_valid(self) -> bool:
        """Check if current token is valid and not expired"""
        return self.auth_token and self.token_expiry and self.token_expiry > datetime.now()

    def get_auth_token(self) -> str:
        """Get current auth token, logging in if needed or token expired"""
        if not self._is_token_valid():
            logger.debug("Auth token expired or missing - attempting login")
            return self.login()
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
            
        except requests.exceptions.HTTPError as e:
            logger.error(
                f"API request failed to {endpoint}. "
                f"Status: {e.response.status_code}, "
                f"Response: {e.response.text}"
            )
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed to {endpoint}: {str(e)}")
            return None
        except ValueError as e:
            logger.error(f"Invalid JSON response from {endpoint}: {str(e)}")
            return None