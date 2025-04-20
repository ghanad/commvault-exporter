import base64
import requests
import logging
from typing import Optional, Dict, Any, Tuple # Added Tuple
from datetime import datetime, timedelta
from urllib.parse import urljoin
import threading # Import threading for lock access

# Import the global cache and lock from the collector module
# Use a relative import to avoid circular dependency issues if possible,
# otherwise structure might need slight adjustment.
# Assuming collector.py is one level up in the directory structure:
# from ..collector.collector import TARGET_TOKEN_CACHE, CACHE_LOCK
# If that causes issues, consider passing the cache/lock or using a separate cache module.
# For simplicity here, we'll assume direct import works or structure allows it.
# **Important**: If direct import causes issues, this needs restructuring.
# Let's try without direct import first and handle cache access differently.

logger = logging.getLogger(__name__)

# --- Placeholder for Cache Access ---
# We need a way for the client to update the cache. Passing functions or the cache itself
# during initialization is one way. Let's try passing update/check functions.

# Define function types for clarity
CacheCheckFunc = Optional[callable] # Should accept target_name, return Optional[Tuple[str, datetime]]
CacheUpdateFunc = Optional[callable] # Should accept target_name, token, expiry_dt

class CommvaultAPIClient:

    
    def __init__(self, target_name: str, target_config: Dict[str, Any]):
        """
        Initializes a new API client instance for a specific target configuration.

        Args:
            target_name: The name of the target this client connects to.
            target_config: A dictionary containing the specific configuration
                           for the target (api_url, username, password, etc.).
        """
        if not target_config:
            raise ValueError("Target configuration dictionary cannot be empty")
        if not target_name:
            raise ValueError("Target name cannot be empty")

        self.target_name = target_name # Store target name
        self.target_config = target_config
        self.auth_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None

        # Extract required configuration
        self.api_url = self.target_config.get('api_url')
        self.username = self.target_config.get('username')
        self.password = self.target_config.get('password')
        self.timeout = self.target_config.get('timeout', 30)
        self.verify_ssl = self.target_config.get('verify_ssl', True)

        if not all([self.api_url, self.username, self.password]):
            missing = [k for k in ['api_url', 'username', 'password'] if not self.target_config.get(k)]
            raise ValueError(f"Target '{self.target_name}': Missing required keys in target configuration: {missing}")

        if '/webconsole' in self.api_url:
             self.base_url = self.api_url.split('/webconsole')[0]
        else:
             self.base_url = self.api_url.rstrip('/')
             logger.warning(f"Target '{self.target_name}': API URL '{self.api_url}' does not contain '/webconsole'. Assuming base URL.")

        if not self.verify_ssl:
            logger.warning(f"Target '{self.target_name}': SSL verification is disabled for API URL {self.api_url}")


    def get_full_url(self, endpoint: str) -> str:
        """Get the full URL for an API endpoint relative to this target's api_url."""
        base_api = self.api_url.rstrip('/') + '/'
        return urljoin(base_api, endpoint.lstrip('/'))

    
    def login(self) -> Tuple[str, datetime]:
        """
        Authenticate with Commvault API for this target.

        Returns:
            Tuple (auth_token, expiry_time) on successful login.

        Raises:
            Exception: If login fails for any reason.
        """
        try:
            encoded_pwd = base64.b64encode(self.password.encode()).decode()
            login_url = self.get_full_url("Login")
            logger.info(f"Target '{self.target_name}': Attempting login to {login_url} as {self.username}")

            headers = { "Content-Type": "application/json", "Accept": "application/json" }
            response = requests.post(
                login_url,
                headers=headers,
                json={"username": self.username, "password": encoded_pwd },
                timeout=self.timeout,
                verify=self.verify_ssl
            )
            response.raise_for_status()
            data = response.json()
            token = data.get('token')

            if not token and 'userName' in data:
                 token = data.get('token')
                 if not token:
                     consoles = data.get('consoles', [])
                     if consoles and isinstance(consoles, list) and len(consoles) > 0:
                          token = consoles[0].get('token')

            if not token:
                logger.error(f"Target '{self.target_name}': Login response missing auth token from {login_url}. Response: {response.text[:500]}")
                raise ValueError(f"Login response missing auth token for {login_url}")

            # Calculate expiry time (e.g., 55 minutes from now)
            expiry_dt = datetime.now() + timedelta(minutes=55)
            logger.info(f"Target '{self.target_name}': Login successful. Token expires around {expiry_dt}.")
            logger.info(f'token: {token}')
            # Return the token and expiry time
            return token, expiry_dt

        except requests.exceptions.HTTPError as e:
            raw_response = getattr(e.response, 'text', 'No response text available')
            status_code = getattr(e.response, 'status_code', 'N/A')
            error_msg = f"Target '{self.target_name}': HTTP error {status_code} during login to {login_url}: {raw_response[:500]}"
            logger.error(error_msg)
            raise Exception(error_msg) from e
        except requests.exceptions.RequestException as e:
            error_msg = f"Target '{self.target_name}': Request failed during login to {login_url}: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e
        except ValueError as e:
            raw_response = getattr(response, 'text', 'No response object or text available') if 'response' in locals() else 'N/A'
            if "Expecting value" in str(e) or isinstance(e, requests.exceptions.JSONDecodeError):
                logger.error(f"Target '{self.target_name}': Invalid JSON response during login to {login_url}. Raw content: {raw_response[:500]}")
                raise Exception(f"Server at {login_url} returned invalid JSON: {raw_response[:500]}") from e
            error_msg = f"Target '{self.target_name}': Data error during login to {login_url}: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            logger.error(f"Target '{self.target_name}': Unexpected error during login to {login_url}: {str(e)}", exc_info=True)
            raise

    def _is_token_valid(self, token: Optional[str], expiry: Optional[datetime]) -> bool:
        """Check if a given token/expiry pair is valid."""
        return token and expiry and expiry > datetime.now()

    
    def get_auth_token(self) -> str:
        """
        Get current auth token for this target.
        Checks local instance -> global cache -> performs login if needed.
        Updates global cache on successful login.
        """
        # 1. Check local instance variable first
        if self._is_token_valid(self.auth_token, self.token_expiry):
            logger.debug(f"Target '{self.target_name}': Using valid token from instance.")
            return self.auth_token

        # 2. Check global cache (thread-safe)
        cached_token: Optional[str] = None
        cached_expiry: Optional[datetime] = None
        try:
            # Access cache defined in collector module
            from ..collector.collector import TARGET_TOKEN_CACHE, CACHE_LOCK
            with CACHE_LOCK:
                if self.target_name in TARGET_TOKEN_CACHE:
                    cached_token, cached_expiry = TARGET_TOKEN_CACHE[self.target_name]
                    logger.debug(f"Target '{self.target_name}': Found token in cache. Expiry: {cached_expiry}")
                else:
                     logger.debug(f"Target '{self.target_name}': No token found in cache.")

            # Validate the cached token
            if self._is_token_valid(cached_token, cached_expiry):
                logger.info(f"Target '{self.target_name}': Using valid token found in global cache.")
                # Update local instance variables from cache
                self.auth_token = cached_token
                self.token_expiry = cached_expiry
                return self.auth_token
            elif cached_token: # Cache exists but is expired
                 logger.info(f"Target '{self.target_name}': Token found in cache but has expired ({cached_expiry}).")

        except ImportError:
             logger.error("Could not import TARGET_TOKEN_CACHE, CACHE_LOCK. Token caching disabled.")
        except Exception as e:
             logger.error(f"Error accessing token cache: {e}", exc_info=True)


        # 3. If no valid token locally or in cache, perform login
        logger.info(f"Target '{self.target_name}': No valid token available, proceeding with login.")
        try:
            new_token, new_expiry = self.login() # login now returns a tuple

            # Update local instance variables
            self.auth_token = new_token
            self.token_expiry = new_expiry

            # Update global cache (thread-safe)
            try:
                from ..collector.collector import TARGET_TOKEN_CACHE, CACHE_LOCK
                with CACHE_LOCK:
                    logger.debug(f"Target '{self.target_name}': Updating global cache with new token expiring at {new_expiry}.")
                    TARGET_TOKEN_CACHE[self.target_name] = (new_token, new_expiry)
            except ImportError:
                 logger.error("Could not import TARGET_TOKEN_CACHE, CACHE_LOCK. Failed to update cache.")
            except Exception as e:
                 logger.error(f"Error updating token cache: {e}", exc_info=True)


            return self.auth_token

        except Exception as login_exc:
            # Login failed, ensure local token is invalidated
            self.auth_token = None
            self.token_expiry = None
            # Log the error and re-raise to signal failure
            logger.error(f"Target '{self.target_name}': Failed to obtain new token via login: {login_exc}")
            raise login_exc # Re-raise the exception from login()

    
    def get(self, endpoint: str, params: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        Make a GET request to the Commvault API for this target.

        Args:
            endpoint: API endpoint path (e.g. '/Job').
            params: Optional query parameters.

        Returns:
            Parsed JSON response dictionary or None on error.
        """
        full_url = None
        try:
            token = self.get_auth_token() # This now handles cache/login logic
            full_url = self.get_full_url(endpoint)
            logger.debug(f"Target '{self.target_name}': Making GET request to: {full_url}")

            headers = { 'Authtoken': token, 'Accept': 'application/json' }
            response = requests.get(
                full_url,
                headers=headers,
                params=params,
                timeout=self.timeout,
                verify=self.verify_ssl
            )
            response.raise_for_status()

            if response.status_code == 204 or not response.content:
                 logger.debug(f"Target '{self.target_name}': Received empty successful response (status {response.status_code}) from {full_url}")
                 return {}

            return response.json()

        except Exception as e:
            # Catch potential errors from get_auth_token() or requests
            url_for_log = full_url if full_url else f"{self.api_url}/{endpoint.lstrip('/')}"
            # Avoid logging the token itself in case of error
            if isinstance(e, requests.exceptions.HTTPError):
                 status_code = getattr(e.response, 'status_code', 'N/A')
                 response_text = getattr(e.response, 'text', 'No response text')[:500]
                 logger.error(f"Target '{self.target_name}': API GET request failed to {url_for_log}. Status: {status_code}, Response: {response_text}")
            elif isinstance(e, requests.exceptions.RequestException):
                 logger.error(f"Target '{self.target_name}': Request failed for {url_for_log}: {str(e)}")
            elif isinstance(e, ValueError): # JSONDecodeError
                 raw_response = getattr(response, 'text', 'No response object or text available') if 'response' in locals() else 'N/A'
                 logger.error(f"Target '{self.target_name}': Invalid JSON response from {url_for_log}: {str(e)}. Response: {raw_response[:500]}")
            else:
                 # Catch errors from get_auth_token (like login failure) or others
                 logger.error(f"Target '{self.target_name}': Unexpected error during GET request to {endpoint} for {url_for_log}: {str(e)}")
            return None # Return None on any exception during GET