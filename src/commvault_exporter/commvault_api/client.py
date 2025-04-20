import base64
import requests
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from urllib.parse import urljoin
# Note: No longer importing ConfigHandler here directly, pass config dict

logger = logging.getLogger(__name__)

class CommvaultAPIClient:
    # Removed Singleton pattern (__new__, _instance, _initialized checks)

    def __init__(self, target_config: Dict[str, Any]):
        """
        Initializes a new API client instance for a specific target configuration.

        Args:
            target_config: A dictionary containing the specific configuration
                           for the target (api_url, username, password, etc.).
        """
        if not target_config:
            raise ValueError("Target configuration dictionary cannot be empty")

        self.target_config = target_config
        self.auth_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None

        # Extract required configuration
        self.api_url = self.target_config.get('api_url')
        self.username = self.target_config.get('username')
        self.password = self.target_config.get('password')
        self.timeout = self.target_config.get('timeout', 30) # Default timeout if not in dict
        self.verify_ssl = self.target_config.get('verify_ssl', True) # Default to verify

        if not all([self.api_url, self.username, self.password]):
            missing = [k for k in ['api_url', 'username', 'password'] if not self.target_config.get(k)]
            raise ValueError(f"Missing required keys in target configuration: {missing}")

        # Store base URL without path for endpoints that don't use /webconsole/api
        # Handle potential case where api_url doesn't contain '/webconsole'
        if '/webconsole' in self.api_url:
             self.base_url = self.api_url.split('/webconsole')[0]
        else:
             # Assume the provided URL is the base if '/webconsole' is missing
             # Or handle as an error if '/webconsole/api' structure is mandatory
             self.base_url = self.api_url.rstrip('/')
             logger.warning(f"API URL '{self.api_url}' does not contain '/webconsole'. "
                            f"Assuming it's the base URL. Login might require adjustments.")


        if not self.verify_ssl:
            logger.warning(f"SSL verification is disabled for target with API URL {self.api_url}")
            # Suppress InsecureRequestWarning for this specific client instance if possible
            # Note: requests.packages.urllib3.disable_warnings is global, so avoid if possible.
            # Better to handle this per-request if verify=False is used.


    def get_full_url(self, endpoint: str) -> str:
        """Get the full URL for an API endpoint relative to this target's api_url."""
        # Ensure api_url ends with / before joining
        base_api = self.api_url.rstrip('/') + '/'
        return urljoin(base_api, endpoint.lstrip('/'))

    def login(self) -> str:
        """Authenticate with Commvault API for this target and store auth token."""
        # Credentials already checked in __init__

        try:
            # Base64 encode the password
            encoded_pwd = base64.b64encode(self.password.encode()).decode()

            # Use the existing helper method which handles trailing slashes correctly
            login_url = self.get_full_url("Login")
            logger.info(f"Attempting login to {login_url} as {self.username}")

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            response = requests.post(
                login_url, # Use the correctly formed URL
                headers=headers,
                json={
                    "username": self.username,
                    "password": encoded_pwd
                },
                timeout=self.timeout,
                verify=self.verify_ssl
            )

            response.raise_for_status() # Check for HTTP errors (4xx, 5xx)

            data = response.json()
            token = data.get('token')

            # Some API versions might return 'token' or 'tokenValue' or similar
            if not token and 'userName' in data: # Check if response looks like a successful login response
                 token = data.get('token') # Try again, maybe structure varies
                 if not token:
                     # Look inside 'consoles' array which is another common pattern
                     consoles = data.get('consoles', [])
                     if consoles and isinstance(consoles, list) and len(consoles) > 0:
                          token = consoles[0].get('token')

            if not token:
                logger.error(f"Login response missing auth token for {login_url}. Response: {response.text[:500]}")
                raise ValueError(f"Login response missing auth token for {login_url}")

            self.auth_token = token
            # Set expiry slightly less than typical token lifetime (often 1 hour)
            self.token_expiry = datetime.now() + timedelta(minutes=55)
            logger.info(f"Login successful for {login_url}")
            return self.auth_token

        except requests.exceptions.HTTPError as e:
            raw_response = getattr(e.response, 'text', 'No response text available')
            status_code = getattr(e.response, 'status_code', 'N/A')
            error_msg = f"HTTP error {status_code} during login to {login_url}: {raw_response[:500]}"
            logger.error(error_msg)
            # Consider raising a more specific exception type if needed elsewhere
            raise Exception(error_msg) from e
        except requests.exceptions.RequestException as e:
            error_msg = f"Request failed during login to {login_url}: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e
        except ValueError as e: # Handles JSONDecodeError as well
            # Check if response exists before trying to access text
            raw_response = getattr(response, 'text', 'No response object or text available')
            if "Expecting value" in str(e) or isinstance(e, requests.exceptions.JSONDecodeError):
                logger.error(f"Invalid JSON response during login to {login_url}. Raw content: {raw_response[:500]}")
                raise Exception(f"Server at {login_url} returned invalid JSON: {raw_response[:500]}") from e
            # Reraise other ValueErrors (like missing token)
            error_msg = f"Data error during login to {login_url}: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            logger.error(f"Unexpected error during login to {login_url}: {str(e)}")
            raise # Re-raise the original exception

    def _is_token_valid(self) -> bool:
        """Check if current token is valid and not expired for this instance."""
        return self.auth_token and self.token_expiry and self.token_expiry > datetime.now()

    def get_auth_token(self) -> str:
        """Get current auth token, logging in if needed or token expired for this instance."""
        if not self._is_token_valid():
            logger.info(f"Auth token invalid or expired for {self.api_url} - attempting login")
            try:
                 return self.login()
            except Exception as e:
                 logger.error(f"Failed to refresh token for {self.api_url}: {e}")
                 # Decide if we should clear the token or just raise
                 self.auth_token = None
                 self.token_expiry = None
                 raise # Re-raise the exception from login()
        # If token is valid, log its presence just for debugging if needed
        # logger.debug(f"Using existing valid auth token for {self.api_url}")
        return self.auth_token # Should always be non-None if no exception was raised

    def get(self, endpoint: str, params: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        Make a GET request to the Commvault API for this target.

        Args:
            endpoint: API endpoint path (e.g. '/Job').
            params: Optional query parameters.

        Returns:
            Parsed JSON response dictionary or None on error.
        """
        full_url = None # Initialize for logging in except blocks
        try:
            token = self.get_auth_token() # Ensures login happens if needed
            full_url = self.get_full_url(endpoint) # Use helper for all endpoints
            logger.debug(f"Making GET request to: {full_url}")

            headers = {
                'Authtoken': token,
                'Accept': 'application/json'
            }

            response = requests.get(
                full_url,
                headers=headers,
                params=params,
                timeout=self.timeout,
                verify=self.verify_ssl
            )

            response.raise_for_status() # Check for HTTP errors

            # Handle potential empty success response (e.g., 204 No Content)
            if response.status_code == 204 or not response.content:
                 logger.debug(f"Received empty successful response (status {response.status_code}) from {full_url}")
                 return {} # Return empty dict for consistency, or None if preferred

            return response.json()

        except requests.exceptions.HTTPError as e:
            status_code = getattr(e.response, 'status_code', 'N/A')
            response_text = getattr(e.response, 'text', 'No response text')[:500]
            # Ensure full_url was assigned before error
            url_for_log = full_url if full_url else f"{self.api_url}/{endpoint.lstrip('/')}"
            logger.error(
                f"API GET request failed to {url_for_log}. "
                f"Status: {status_code}, "
                f"Response: {response_text}"
            )
            # Optionally, re-raise or return a specific error indicator
            return None
        except requests.exceptions.RequestException as e:
            # Network errors, timeouts, DNS errors etc.
            url_for_log = full_url if full_url else f"{self.api_url}/{endpoint.lstrip('/')}"
            logger.error(f"Request failed for {url_for_log}: {str(e)}")
            return None
        except ValueError as e: # Handles JSONDecodeError
            raw_response = getattr(response, 'text', 'No response object or text available')
            url_for_log = full_url if full_url else f"{self.api_url}/{endpoint.lstrip('/')}"
            logger.error(f"Invalid JSON response from {url_for_log}: {str(e)}. Response: {raw_response[:500]}")
            return None
        except Exception as e:
            # Catch potential errors from get_auth_token() or other unexpected issues
            url_for_log = full_url if full_url else f"{self.api_url}/{endpoint.lstrip('/')}"
            logger.error(f"Unexpected error during GET request to {endpoint} for {url_for_log}: {str(e)}")
            return None