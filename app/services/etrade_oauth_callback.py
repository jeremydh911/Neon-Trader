"""
E*TRADE OAuth Callback Handler
Implements callback-based OAuth flow with HTTPS support
Automatically captures verification code from E*TRADE redirect
"""

import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Callable
import json
import time

logger = logging.getLogger(__name__)


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback"""
    
    # Class variables (must set on the class, not self — handler is per-request)
    verification_code: Optional[str] = None
    oauth_token: Optional[str] = None
    callback_received = threading.Event()
    
    def do_GET(self):
        """Handle GET request from E*TRADE callback"""
        
        # Parse URL and query parameters
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        
        logger.info(f"OAuth callback received: {self.path}")
        
        # Extract verification code (and request token if E*TRADE sent it)
        if 'oauth_verifier' in query_params:
            OAuthCallbackHandler.verification_code = query_params['oauth_verifier'][0]
            token_vals = query_params.get('oauth_token') or []
            OAuthCallbackHandler.oauth_token = token_vals[0] if token_vals else None
            logger.info("Verification code received")
            
            # Send success response
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            response_html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>E*TRADE Authorization Successful</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 3rem;
                        border-radius: 10px;
                        box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                        text-align: center;
                    }
                    h1 {
                        color: #28a745;
                        margin: 0 0 1rem 0;
                    }
                    p {
                        color: #666;
                        margin: 0.5rem 0;
                    }
                    .code {
                        background: #f0f0f0;
                        padding: 1rem;
                        border-radius: 5px;
                        font-family: monospace;
                        font-weight: bold;
                        margin: 1rem 0;
                        word-break: break-all;
                    }
                    .button {
                        background: #667eea;
                        color: white;
                        padding: 0.75rem 1.5rem;
                        border: none;
                        border-radius: 5px;
                        cursor: pointer;
                        font-size: 1rem;
                        margin-top: 1rem;
                    }
                    .button:hover {
                        background: #764ba2;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>✅ Authorization Successful!</h1>
                    <p>Your E*TRADE application has been authorized.</p>
                    <p>Verification code has been automatically captured.</p>
                    <p>You can now close this window and return to the application.</p>
                    <button class="button" onclick="window.close()">Close Window</button>
                </div>
                <script>
                    // Auto-close after 3 seconds
                    setTimeout(function() {
                        window.close();
                    }, 3000);
                </script>
            </body>
            </html>
            """
            self.wfile.write(response_html.encode('utf-8'))
            
            # Signal that callback was received
            self.callback_received.set()
        
        else:
            # No verification code found
            logger.error(f"No oauth_verifier in callback: {query_params}")
            
            self.send_response(400)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            error_html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authorization Failed</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 3rem;
                        border-radius: 10px;
                        box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                        text-align: center;
                    }
                    h1 {
                        color: #dc3545;
                        margin: 0 0 1rem 0;
                    }
                    p {
                        color: #666;
                        margin: 0.5rem 0;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>❌ Authorization Failed</h1>
                    <p>The authorization callback did not include a verification code.</p>
                    <p>Please try again.</p>
                </div>
            </body>
            </html>
            """
            self.wfile.write(error_html.encode('utf-8'))
    
    def log_message(self, format, *args):
        """Suppress default HTTP server logging"""
        pass


class OAuthCallbackServer:
    """Manages local HTTP server for OAuth callback"""
    
    def __init__(self, host: str = 'localhost', port: int = 8080, use_https: bool = False):
        """
        Initialize callback server
        
        Args:
            host: Server hostname
            port: Server port
            use_https: Whether to use HTTPS (requires certificate)
        """
        self.host = host
        self.port = port
        self.use_https = use_https
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.verification_code: Optional[str] = None
        self.oauth_token: Optional[str] = None
        
        logger.info(f"OAuth Callback Server initialized: {self.get_callback_url()}")
    
    def get_callback_url(self) -> str:
        """Get the full callback URL"""
        protocol = "https" if self.use_https else "http"
        return f"{protocol}://{self.host}:{self.port}/authorize"
    
    def start(self) -> bool:
        """
        Start the callback server in background thread
        
        Returns:
            True if server started successfully
        """
        try:
            self.server = HTTPServer((self.host, self.port), OAuthCallbackHandler)
            
            # Start server in background thread
            self.thread = threading.Thread(
                target=self.server.serve_forever,
                daemon=True
            )
            self.thread.start()
            
            logger.info(f"✅ OAuth Callback Server started on {self.get_callback_url()}")
            return True
        
        except Exception as e:
            logger.error(f"❌ Failed to start OAuth Callback Server: {e}")
            return False
    
    def stop(self):
        """Stop the callback server"""
        if self.server:
            self.server.shutdown()
            logger.info("OAuth Callback Server stopped")
    
    def wait_for_callback(self, timeout: int = 600) -> Optional[str]:
        """
        Wait for OAuth callback and return verification code
        
        Args:
            timeout: Maximum time to wait in seconds (default 10 minutes)
        
        Returns:
            Verification code if received, None if timeout
        """
        if not OAuthCallbackHandler.callback_received.wait(timeout=timeout):
            logger.warning(f"OAuth callback timeout after {timeout}s")
            return None
        
        verification_code = OAuthCallbackHandler.verification_code
        oauth_token = OAuthCallbackHandler.oauth_token
        logger.info("Verification code captured")
        self.verification_code = verification_code
        self.oauth_token = oauth_token

        # Reset for next callback
        OAuthCallbackHandler.callback_received.clear()
        OAuthCallbackHandler.verification_code = None
        OAuthCallbackHandler.oauth_token = None

        return verification_code


class ETradeOAuthCallbackFlow:
    """E*TRADE OAuth flow with callback support"""
    
    def __init__(self, oauth_service, callback_host: str = 'localhost', callback_port: int = 8080):
        """
        Initialize OAuth callback flow
        
        Args:
            oauth_service: ETradeOAuthService instance
            callback_host: Callback server hostname
            callback_port: Callback server port
        """
        self.oauth_service = oauth_service
        self.callback_server = OAuthCallbackServer(host=callback_host, port=callback_port)
        
        logger.info(f"OAuth Callback Flow initialized")
    
    def get_authorization_flow_info(self) -> Dict:
        """
        Get authorization flow information
        
        Returns:
            Dict with authorization_url and callback_url
        """
        # Start callback server
        if not self.callback_server.start():
            return {
                'success': False,
                'error': 'Failed to start callback server'
            }
        
        # Initiate OAuth flow
        authorization_url = self.oauth_service.initiate_oauth_flow()
        
        if not authorization_url:
            return {
                'success': False,
                'error': 'Failed to get authorization URL'
            }
        
        return {
            'success': True,
            'authorization_url': authorization_url,
            'callback_url': self.callback_server.get_callback_url(),
            'instructions': {
                'step1': 'Click the authorization URL to open in browser',
                'step2': 'Login with E*TRADE credentials',
                'step3': 'Grant permission to AhanaTrade',
                'step4': 'You will be redirected - verification code auto-captured',
                'step5': 'Return to app when callback completes'
            }
        }
    
    def complete_oauth_flow(self, timeout: int = 600) -> bool:
        """
        Wait for callback and complete OAuth flow
        
        Args:
            timeout: Maximum time to wait for callback
        
        Returns:
            True if OAuth flow completed successfully
        """
        # Wait for callback with verification code
        verification_code = self.callback_server.wait_for_callback(timeout=timeout)
        
        if not verification_code:
            logger.error("OAuth callback timeout - verification code not received")
            self.callback_server.stop()
            return False
        
        # Complete via reconstructed session from JSON request-token material
        try:
            result = self.oauth_service.complete_oauth_flow(
                verification_code,
                request_token=self.callback_server.oauth_token,
            )
            logger.info("OAuth flow completed")
            return result
        
        finally:
            # Stop callback server
            self.callback_server.stop()
    
    def get_status(self) -> Dict:
        """Get OAuth status"""
        return {
            'callback_server_running': self.callback_server.server is not None,
            'callback_url': self.callback_server.get_callback_url(),
            'oauth_service_status': self.oauth_service.get_status()
        }


# Singleton instance
_oauth_callback_flow = None


def get_etrade_oauth_callback_flow(oauth_service=None, host: str = 'localhost', 
                                   port: int = 8080) -> ETradeOAuthCallbackFlow:
    """Get or create OAuth callback flow instance"""
    global _oauth_callback_flow
    
    if _oauth_callback_flow is None and oauth_service is not None:
        _oauth_callback_flow = ETradeOAuthCallbackFlow(oauth_service, host, port)
    
    return _oauth_callback_flow
