"""
JWT cookie authentication for PraisonAI Gateway.

Provides secure, HttpOnly JWT cookies for session management
using itsdangerous (available via Starlette dependency).
"""

import json
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Union

try:
    from itsdangerous import TimestampSigner, BadSignature, SignatureExpired
    ITSDANGEROUS_AVAILABLE = True
except ImportError:
    ITSDANGEROUS_AVAILABLE = False
    # Fallback for when itsdangerous is not available
    TimestampSigner = None
    BadSignature = Exception
    SignatureExpired = Exception


class CookieAuthManager:
    """JWT cookie authentication manager using itsdangerous.
    
    Features:
    - Secure JWT-style tokens using itsdangerous
    - HttpOnly, SameSite=Strict cookies
    - Configurable expiration time
    - HTTPS-aware Secure flag
    
    Example:
        auth = CookieAuthManager(secret_key="your-secret")
        
        # Create a session cookie
        cookie_value = auth.create_session(user_id="12345")
        
        # Verify a session cookie
        session = auth.verify_session(cookie_value)
        if session:
            user_id = session.get("user_id")
    """
    
    def __init__(
        self,
        secret_key: str,
        cookie_name: str = "praisonai_session",
        max_age: int = 86400,  # 24 hours
    ):
        """Initialize cookie auth manager.
        
        Args:
            secret_key: Secret key for signing tokens
            cookie_name: Name of the cookie
            max_age: Cookie max age in seconds (24 hours default)
        """
        if not ITSDANGEROUS_AVAILABLE:
            raise ImportError(
                "itsdangerous is required for cookie authentication. "
                "Install with: pip install praisonai[api]"
            )
        
        self.secret_key = secret_key
        self.cookie_name = cookie_name
        self.max_age = max_age
        self.signer = TimestampSigner(secret_key)
    
    def create_session(self, **claims) -> str:
        """Create a signed session token with claims.
        
        Args:
            **claims: Arbitrary session claims (e.g., user_id, roles)
            
        Returns:
            Signed session token
        """
        if not ITSDANGEROUS_AVAILABLE:
            raise RuntimeError("itsdangerous not available")
        
        # Validate claims don't contain reserved keys
        reserved_keys = {"iat", "exp"}
        if reserved_keys & claims.keys():
            raise ValueError(f"Claims cannot contain reserved keys: {reserved_keys & claims.keys()}")
        
        # Add standard claims
        now = int(time.time())
        payload = {
            "iat": now,
            "exp": now + self.max_age,
            **claims
        }
        
        # Convert to JSON and sign
        payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return self.signer.sign(payload_str.encode()).decode()
    
    def verify_session(self, token: str) -> Optional[Dict[str, Union[str, int]]]:
        """Verify and decode a session token.
        
        Args:
            token: Signed session token
            
        Returns:
            Claims dict if valid, None if invalid/expired
        """
        if not ITSDANGEROUS_AVAILABLE or not token:
            return None
        
        try:
            # Verify signature and timestamp
            payload_str = self.signer.unsign(
                token.encode(),
                max_age=self.max_age
            ).decode()
            
            # Parse claims from JSON
            claims = json.loads(payload_str)
            
            # Check expiration
            exp = claims.get("exp")
            if exp and exp < time.time():
                return None
            
            return claims
            
        except (BadSignature, SignatureExpired, ValueError, TypeError):
            return None
    
    def create_cookie_header(
        self,
        token: str,
        secure: bool = True,
        http_only: bool = True,
        same_site: str = "Strict",
        path: str = "/",
    ) -> str:
        """Create a Set-Cookie header string.
        
        Args:
            token: Session token
            secure: Whether to set Secure flag
            http_only: Whether to set HttpOnly flag
            same_site: SameSite policy ("Strict", "Lax", or "None")
            path: Cookie path
            
        Returns:
            Set-Cookie header value
        """
        cookie_parts = [f"{self.cookie_name}={token}"]
        
        if http_only:
            cookie_parts.append("HttpOnly")
        
        if secure:
            cookie_parts.append("Secure")
        
        if same_site:
            cookie_parts.append(f"SameSite={same_site}")
        
        if path:
            cookie_parts.append(f"Path={path}")
        
        if self.max_age:
            cookie_parts.append(f"Max-Age={self.max_age}")
        
        return "; ".join(cookie_parts)
    
    def create_clear_cookie_header(
        self,
        path: str = "/",
    ) -> str:
        """Create a Set-Cookie header to clear the session cookie.
        
        Args:
            path: Cookie path
            
        Returns:
            Set-Cookie header value to clear the cookie
        """
        cookie_parts = [
            f"{self.cookie_name}=",
            "Max-Age=0",
            "HttpOnly",
            f"Path={path}",
        ]
        return "; ".join(cookie_parts)
    
    def extract_token_from_cookies(self, cookie_header: str) -> Optional[str]:
        """Extract session token from Cookie header.
        
        Args:
            cookie_header: Cookie header value
            
        Returns:
            Session token if found, None otherwise
        """
        if not cookie_header:
            return None
        
        # Parse cookies
        cookies = {}
        for cookie in cookie_header.split(";"):
            cookie = cookie.strip()
            if "=" in cookie:
                name, value = cookie.split("=", 1)
                cookies[name.strip()] = value.strip()
        
        return cookies.get(self.cookie_name)
    
    def is_token_valid(self, token: str) -> bool:
        """Check if a token is valid without extracting claims.
        
        Args:
            token: Session token
            
        Returns:
            True if valid, False otherwise
        """
        return self.verify_session(token) is not None


def create_auth_manager_from_env() -> Optional[CookieAuthManager]:
    """Create a CookieAuthManager using environment variables.
    
    Looks for GATEWAY_AUTH_TOKEN or PRAISONAI_SECRET_KEY.
    
    Returns:
        CookieAuthManager if secret available, None otherwise
    """
    import os
    
    secret = (
        os.environ.get("GATEWAY_AUTH_TOKEN") or 
        os.environ.get("PRAISONAI_SECRET_KEY")
    )
    
    if not secret:
        return None
    
    return CookieAuthManager(secret_key=secret)