import base64
import requests
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from urllib.parse import urljoin
from ..config_handler import ConfigHandler

logger = logging.getLogger(__name__)

class CommvaultAPIClient:
    _instance = None
    
    def __new__(cls, config: ConfigHandler):
        if cls._instance is None:
            cls._instance = super(CommvaultAPIClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
        
    def __init__(self, config: ConfigHandler):
        if self._initialized:
            return
        self._initialized = True
        self.config = config
        self.auth_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self.api_url = self.config.get('commvault', 'api_url')
        self.username = self.config.get('commvault', 'username')
        self.password = self.config.get('commvault', 'password')
        # Store base URL without path for endpoints that don't use /webconsole/api
        self.base_url = self.api_url.split('/webconsole')[0]
        if not self.config.get('exporter', 'verify_ssl', default=True):
            logger.warning("SSL verification is disabled - using self-signed certificates")
    
    def get_full_url(self, endpoint: str) -> str:
        """Get the full URL for an API endpoint"""
        if endpoint == "Login":
            return f"{self.api_url}/Login"
        return urljoin(self.api_url.rstrip('/') + '/', endpoint.lstrip('/'))

    def login(self) -> str:
        """Authenticate with Commvault API and store auth token"""
        if not all([self.api_url, self.username, self.password]):
            error_msg = "Missing required configuration for API login"
            logger.error(error_msg)
            raise ValueError(error_msg)

        try:
            # Base64 encode the password
            encoded_pwd = base64.b64encode(self.password.encode()).decode()

            logger.info(f"Attempting login to {self.api_url} as {self.username}")
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            full_url = f"{self.api_url}/Login"
            logger.info(f"Making POST request to: {full_url}")
            response = requests.post(
                f"{self.api_url}/Login",  # Use explicit full path for login
                headers=headers,
                json={
                    "username": self.username,
                    "password": encoded_pwd
                },
                timeout=self.config.get('exporter', 'timeout'),
                verify=self.config.get('exporter', 'verify_ssl', default=True)
            )
            
            # Check for HTTP errors
            response.raise_for_status()

            # Process response and store token
            data = response.json()
            if not data.get('token'):
                raise ValueError("Login response missing auth token")
                
            self.auth_token = data['token']
            self.token_expiry = datetime.now() + timedelta(hours=1)  # Tokens typically expire after 1 hour
            logger.info("Login successful")
            logger.info(f"token: {self.auth_token}")
            return self.auth_token

        except requests.exceptions.HTTPError as e:
            raw_response = getattr(e.response, 'text', 'No response text available')
            logger.debug(f"Raw error response: {raw_response}")
            error_msg = f"HTTP error during login: {e.response.status_code} - {raw_response}"
            logger.error(error_msg)
            raise Exception(error_msg) from e
        except requests.exceptions.RequestException as e:
            error_msg = f"Request failed during login: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e
        except ValueError as e:
            if "Expecting value" in str(e):
                raw_response = getattr(response, 'text', 'No response text available')
                logger.error(f"Invalid JSON response. Raw content: {raw_response}")
                raise Exception(f"Server returned invalid JSON: {raw_response}") from e
            error_msg = f"Invalid response format during login: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            raise

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
            # For non-login endpoints, try both with and without /webconsole/api
            url = urljoin(self.api_url.rstrip('/') + '/', endpoint.lstrip('/'))
            logger.info(f'full url: {url}')
            
            # Prepare headers
            headers = {
                'Authtoken': token,
                'Accept': 'application/json'
            }
                        
            # Make the request
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=self.config.get('exporter', 'timeout'),
                verify=self.config.get('exporter', 'verify_ssl', default=True)
            )

            # Check for errors
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            full_url = urljoin(self.api_url, endpoint)
            logger.error(
                f"API request failed to {full_url}. "
                f"Status: {e.response.status_code}, "
                f"Response: {e.response.text}"
            )
            return None
        except requests.exceptions.RequestException as e:
            full_url = urljoin(self.api_url, endpoint)
            logger.error(f"Request failed to {full_url}: {str(e)}")
            return None
        except ValueError as e:
            logger.error(f"Invalid JSON response from {endpoint}: {str(e)}")
            return None