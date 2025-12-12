"""
E*TRADE OAuth Service with resilience and retry logic
Handles authentication flow with exponential backoff for transient failures
"""

import os
import sys
import json
import logging
import pickle
from datetime import datetime, timedelta
from pathlib import Path

# Force fresh import of pyetrade (fixes Streamlit caching)
if 'pyetrade' in sys.modules:
    del sys.modules['pyetrade']
if 'pyetrade.authorization' in sys.modules:
    del sys.modules['pyetrade.authorization']

try:
    from pyetrade import ETradeOAuth
    logger = logging.getLogger(__name__)
    logger.info("✅ pyetrade imported successfully")
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.error(f"❌ Failed to import pyetrade: {e}")
    ETradeOAuth = None


class ETradeOAuthService:
    """
    E*TRADE OAuth Service with resilience and retry logic
    Handles authentication flow with exponential backoff for transient failures
    """

    def __init__(self, credentials_file: str = None):
        # Try multiple possible locations for credentials file
        self.credentials_file = credentials_file or os.getenv('ETRADE_CREDENTIALS_FILE')
        
        if not self.credentials_file:
            # Try multiple standard locations
            possible_paths = [
                '/app/config/etrade-credentials.json',  # Docker container
                os.path.join(os.path.dirname(__file__), '..', 'config', 'etrade-credentials.json'),  # Relative to this file
                os.path.join(os.getcwd(), 'app', 'config', 'etrade-credentials.json'),  # From project root
                os.path.expanduser('~/Desktop/neon-trader-gpu/app/config/etrade-credentials.json'),  # Expanded home
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    self.credentials_file = path
                    logger.info(f"Found credentials file at: {self.credentials_file}")
                    break
            
            if not self.credentials_file:
                self.credentials_file = '/app/config/etrade-credentials.json'  # Default fallback
        
        self.tokens_file = '/app/config/.etrade_tokens'
        self.credentials = self._load_credentials()
        self.oauth = None
        self.client = None
        self.is_authenticated = False
        self.last_auth_time = None
        self.token_expiry = None
        self.request_token = None

        logger.info("✅ ETradeOAuthService initialized")

    def _load_credentials(self) -> dict:
        """Load E*TRADE credentials from JSON file"""
        try:
            with open(self.credentials_file, 'r') as f:
                creds = json.load(f)
            logger.info(f"✅ Credentials loaded from {self.credentials_file}")
            return creds
        except FileNotFoundError:
            logger.error(f"❌ Credentials file not found: {self.credentials_file}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"❌ Invalid JSON in credentials file: {e}")
            return {}

    def initiate_oauth_flow(self) -> str:
        """
        Initiate OAuth flow with retry logic for transient failures
        Returns authorization URL for user to visit, or raises exception on error
        """
        import sys
        logger.info(f"DEBUG: Python version: {sys.version}")
        logger.info(f"DEBUG: Python executable: {sys.executable}")
        logger.info(f"DEBUG: Module name: {__name__}")
        logger.info(f"DEBUG: ETradeOAuth = {ETradeOAuth}")
        logger.info(f"DEBUG: ETradeOAuth type = {type(ETradeOAuth)}")
        logger.info(f"DEBUG: ETradeOAuth is None = {ETradeOAuth is None}")
        logger.info(f"DEBUG: not ETradeOAuth = {not ETradeOAuth}")
        
        if not ETradeOAuth:
            logger.error('❌ pyetrade not installed - ETradeOAuth is None or falsy')
            # Double-check by trying to import directly
            try:
                from pyetrade import ETradeOAuth as DirectImport
                logger.error(f"  (But direct import works: {DirectImport})")
            except Exception as e:
                logger.error(f"  (Direct import also failed: {e})")
            raise Exception('pyetrade not installed. Install with: pip install pyetrade')

        if not self.credentials or 'etrade' not in self.credentials:
            logger.error('Credentials not loaded')
            raise Exception('E*TRADE credentials file missing or invalid')

        max_retries = 3
        retry_delay = 2  # seconds

        for attempt in range(max_retries):
            try:
                logger.info(f"Initiating OAuth flow (attempt {attempt + 1}/{max_retries})")

                self.oauth = ETradeOAuth(
                    consumer_key=self.credentials['etrade']['oauth']['consumer_key'],
                    consumer_secret=self.credentials['etrade']['oauth']['consumer_secret'],
                    callback_url='oob'  # Out of Band - user enters verification code manually
                )

                # Get request token
                request_token = self.oauth.get_request_token()
                logger.info("✅ Request token obtained")

                # Generate authorization URL
                auth_url = self.oauth.auth_token_url
                logger.info(f"✅ Authorization URL generated: {auth_url}")

                # Store request token for later
                self.request_token = request_token
                
                return auth_url

            except Exception as e:
                logger.warning(f"⚠️  OAuth initiation failed (attempt {attempt + 1}): {e}")

                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"❌ OAuth initiation failed after {max_retries} attempts: {e}")
                    raise Exception(f'Failed to initiate OAuth flow: {str(e)}')

        raise Exception('Max retries exceeded for OAuth flow initiation')

    def complete_oauth_flow(self, verification_code: str) -> bool:
        """
        Complete OAuth flow with verification code
        Exchanges code for access tokens
        Returns True on success, raises exception on failure
        """
        try:
            if not self.oauth:
                logger.error("OAuth not initialized - call initiate_oauth_flow first")
                raise Exception('Please start the OAuth flow first')

            logger.info("Exchanging verification code for access tokens")

            # Exchange verification code for access tokens
            self.oauth.get_access_token(verification_code)
            logger.info("✅ Access tokens obtained")

            # Get tokens
            access_token = self.oauth.access_token
            access_token_secret = self.oauth.resource_owner_key

            # Save tokens securely
            self._save_access_tokens({
                'access_token': access_token,
                'access_token_secret': access_token_secret
            })

            # Update state
            self.is_authenticated = True
            self.last_auth_time = datetime.now()
            self.token_expiry = datetime.now() + timedelta(hours=24)

            logger.info("✅ OAuth flow completed successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to complete OAuth flow: {e}")
            raise Exception(f'Failed to exchange verification code: {str(e)}')

    def load_cached_tokens(self) -> bool:
        """Load previously saved access tokens"""
        try:
            with open(self.tokens_file, 'rb') as f:
                tokens = pickle.load(f)

            if not ETradeOAuth:
                logger.error("pyetrade not installed")
                return False

            self.oauth = ETradeOAuth(
                consumer_key=self.credentials['etrade']['oauth']['consumer_key'],
                consumer_secret=self.credentials['etrade']['oauth']['consumer_secret'],
                callback_url='oob'
            )

            # Manually set tokens
            self.oauth.access_token = tokens['access_token']
            self.oauth.resource_owner_key = tokens['access_token_secret']

            self.is_authenticated = True
            self.last_auth_time = tokens.get('saved_time')
            logger.info("✅ Cached tokens loaded successfully")
            return True

        except FileNotFoundError:
            logger.info("No cached tokens found")
            return False
        except Exception as e:
            logger.warning(f"⚠️  Failed to load cached tokens: {e}")
            return False

    def _save_access_tokens(self, tokens: dict):
        """Save access tokens securely"""
        try:
            os.makedirs(os.path.dirname(self.tokens_file), exist_ok=True)
            tokens['saved_time'] = datetime.now().isoformat()

            with open(self.tokens_file, 'wb') as f:
                pickle.dump(tokens, f)

            # Set restrictive permissions
            os.chmod(self.tokens_file, 0o600)
            logger.info(f"✅ Access tokens saved securely to {self.tokens_file}")
        except Exception as e:
            logger.error(f"❌ Failed to save access tokens: {e}")

    def get_status(self) -> dict:
        """Get current authentication status"""
        needs_refresh = False
        if self.token_expiry:
            needs_refresh = datetime.now() > self.token_expiry
        
        return {
            'is_authenticated': self.is_authenticated,
            'auth_time': self.last_auth_time.isoformat() if self.last_auth_time else None,
            'expiry_time': self.token_expiry.isoformat() if self.token_expiry else None,
            'needs_refresh': needs_refresh
        }
