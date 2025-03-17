#!/usr/bin/env python3
"""
Peplink API Client - Async API class for interacting with the Peplink router API

This module provides the PeplinkAPI class that connects to a Peplink router's local API,
authenticates, and retrieves information about WAN status and connected clients.
"""
from __future__ import annotations

import logging
import json
import ssl
import asyncio
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
from functools import partial
import time

import aiohttp

_LOGGER = logging.getLogger(__name__)


class PeplinkAuthFailed(Exception):
    """Authentication failed."""


class PeplinkSSLError(Exception):
    """SSL Certificate validation error."""


def _create_insecure_ssl_context():
    """Create an insecure SSL context (non-blocking function)."""
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    return ssl_context


class PeplinkAPI:
    """Async class for interacting with the Peplink router API."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        session: Optional[aiohttp.ClientSession] = None,
        verify_ssl: bool = True,
    ):
        """Initialize the Peplink API client."""
        self.host = host  # Store the host for reference
        self.base_url = f"https://{host}"
        self.username = username
        self.password = password
        self._session = session
        self._verify_ssl = verify_ssl
        self._own_session = False
        self._connected = False
        self._auth_cookie = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create a session with the appropriate SSL settings."""
        if not self._session:
            if self._verify_ssl:
                # Create a standard session
                self._session = aiohttp.ClientSession()
            else:
                # Create a session with SSL verification disabled
                ssl_context = _create_insecure_ssl_context()
                connector = aiohttp.TCPConnector(
                    ssl=ssl_context,
                    verify_ssl=False
                )
                self._session = aiohttp.ClientSession(connector=connector)
                
            self._own_session = True
        
        return self._session

    async def connect(self) -> bool:
        """Connect to the Peplink router and authenticate."""
        if self._connected:
            return True
        
        # Create or get a session object
        session = await self._get_session()
        
        try:
            # Step 1: Login to get a cookie
            login_url = urljoin(self.base_url, "/api/login")
            
            login_data = {
                "username": self.username,
                "password": self.password,
                "challenge": "challenge"  # Required by Peplink API
            }
            
            _LOGGER.debug("Attempting to connect to %s", login_url)
            
            try:
                async with session.post(login_url, json=login_data) as response:
                    if response.status == 401:
                        _LOGGER.error("Failed to authenticate: 401 Unauthorized")
                        return False
                    
                    response.raise_for_status()
                    login_response = await response.json()
                    
                    # Check for successful login
                    if login_response.get("stat") != "ok":
                        _LOGGER.error("Failed to authenticate: %s", login_response.get("message", "Unknown error"))
                        return False
                    
                    # Parse cookie from response
                    cookies = response.cookies
                    _LOGGER.debug("Cookies from response: %s", cookies)
                    
                    # Extract the bauth cookie
                    if "bauth" in cookies:
                        self._auth_cookie = cookies["bauth"].value
                        _LOGGER.debug("Got auth cookie: %s", self._auth_cookie)
                    
                    if not self._auth_cookie:
                        # Try extracting from Set-Cookie header if available
                        if "Set-Cookie" in response.headers:
                            cookie_header = response.headers["Set-Cookie"]
                            _LOGGER.debug("Set-Cookie header: %s", cookie_header)
                            
                            if "bauth=" in cookie_header:
                                # Extract the bauth value from cookie header
                                # Format is typically: bauth=VALUE; path=/; HttpOnly
                                cookie_parts = cookie_header.split(';')
                                for part in cookie_parts:
                                    if part.strip().startswith("bauth="):
                                        self._auth_cookie = part.strip().split('=', 1)[1]
                                        _LOGGER.debug("Extracted bauth cookie from header: %s", self._auth_cookie)
                                        break
                    
                    if not self._auth_cookie:
                        _LOGGER.error("No auth cookie received after login")
                        return False
            except aiohttp.ClientConnectorCertificateError as e:
                _LOGGER.error("SSL Certificate error: %s", e)
                self._connected = False
                raise PeplinkSSLError(f"SSL Certificate validation failed: {e}")
                
            # Step 3: Verify that we're authenticated by accessing a protected endpoint
            verify_url = urljoin(self.base_url, "/api/status")
            
            # Ensure cookie is set for verification request
            headers = {}
            if self._auth_cookie:
                headers["Cookie"] = f"bauth={self._auth_cookie}"
                _LOGGER.debug("Using stored auth cookie for verification request: %s", headers["Cookie"])
            
            async with session.get(verify_url, headers=headers) as response:
                if response.status == 401:
                    _LOGGER.error("Failed to authenticate: 401 Unauthorized")
                    return False
                
                response.raise_for_status()
                verify_data = await response.json()
                
                # Even if it returns an error code (other than 401), it's fine as long as we can access it
                _LOGGER.debug("Authentication verification successful: %s", verify_data)
            
            self._connected = True
            return True
            
        except PeplinkSSLError:
            # Re-raise SSL errors so they can be handled differently from auth errors
            raise
        except aiohttp.ClientConnectorError as e:
            _LOGGER.error("Connection error (host unreachable): %s", e)
            self._connected = False
            return False
        except aiohttp.ClientError as e:
            _LOGGER.error("Connection error: %s", e)
            self._connected = False
            return False

    async def ensure_connected(self, force_reconnect: bool = False) -> bool:
        """Ensure that a connection has been established.
        
        Args:
            force_reconnect: If True, will reconnect even if already connected
        
        Returns:
            bool: True if successfully connected, False otherwise
        """
        if not self._connected or force_reconnect:
            self._connected = False  # Reset connected state if forcing reconnect
            return await self.connect()
        return True
    
    async def _api_request(self, endpoint: str, method: str = "GET", data: Optional[Dict] = None) -> Dict:
        """Make an API request to the Peplink router."""
        if not self._connected:
            # Try to connect first
            _LOGGER.debug("Not connected, attempting to connect first")
            if not await self.connect():
                raise Exception("Not connected to Peplink router")
        
        session = await self._get_session()
        url = urljoin(self.base_url, endpoint)
        
        headers = {}
        # Manually add cookie to request if available
        if self._auth_cookie:
            headers["Cookie"] = f"bauth={self._auth_cookie}"
            _LOGGER.debug("Adding auth cookie to request: %s", headers["Cookie"])
        
        try:
            async with session.request(method, url, json=data, headers=headers) as response:
                # Check for authentication error
                if response.status == 401:
                    _LOGGER.error("API error: Unauthorized (code: 401)")
                    # Try to reconnect with force flag and retry the request
                    if await self.ensure_connected(force_reconnect=True):
                        _LOGGER.debug("Successfully reconnected, retrying request")
                        headers = {}
                        if self._auth_cookie:
                            headers["Cookie"] = f"bauth={self._auth_cookie}"
                        async with session.request(method, url, json=data, headers=headers) as retry_response:
                            if retry_response.status == 401:
                                _LOGGER.error("Still unauthorized after reconnect attempt")
                                raise Exception("Unauthorized (code: 401)")
                            retry_response.raise_for_status()
                            response_data = await retry_response.json()
                            if response_data.get("stat") == "fail" and response_data.get("code") == 401:
                                _LOGGER.error("Authentication failed with API error 401 after reconnect")
                                raise Exception("Unauthorized API response (code: 401)")
                            return response_data
                    else:
                        raise Exception("Failed to reconnect, unauthorized (code: 401)")
                
                # Raise other HTTP errors
                response.raise_for_status()
                
                # Check for API-level auth errors in response
                response_data = await response.json()
                if response_data.get("stat") == "fail" and response_data.get("code") == 401:
                    _LOGGER.error("Authentication failed with API error 401")
                    # Try to reconnect with force flag and retry
                    if await self.ensure_connected(force_reconnect=True):
                        _LOGGER.debug("Successfully reconnected after API 401, retrying request")
                        headers = {}
                        if self._auth_cookie:
                            headers["Cookie"] = f"bauth={self._auth_cookie}"
                        async with session.request(method, url, json=data, headers=headers) as retry_response:
                            retry_response.raise_for_status()
                            retry_data = await retry_response.json()
                            if retry_data.get("stat") == "fail" and retry_data.get("code") == 401:
                                _LOGGER.error("Still getting API-level 401 after reconnect")
                                raise Exception("Unauthorized API response after reconnect (code: 401)")
                            return retry_data
                    else:
                        raise Exception("Failed to reconnect for API-level 401 error")
                
                # Return parsed JSON response
                return response_data
                
        except aiohttp.ClientError as e:
            _LOGGER.error("API request error: %s", e)
            raise Exception(f"API request error: {e}")

    async def _format_api_url(self, func: str, public_api: bool = False, **kwargs) -> str:
        """Format an API URL based on the function pattern and additional parameters.
        
        Args:
            func: The API function to call (e.g., 'status.client' or 'status.traffic')
            public_api: If True, use the /api/ style endpoint, otherwise use the cgi-bin style
            **kwargs: Additional URL parameters to include
            
        Returns:
            str: Formatted API URL
        """
        if public_api:
            # Use "/api/..." style endpoint
            # Remove leading slash if present to ensure consistent formatting
            if func.startswith('/'):
                func = func[1:]
            endpoint = f"/api/{func}"
        else:
            # Use "/cgi-bin/MANGA/api.cgi?func=..." style endpoint
            # Add timestamp to prevent caching
            params = {
                "func": func,
                "_": str(int(time.time() * 1000))
            }
            
            # Add any additional parameters
            params.update(kwargs)
            
            # Build query string
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            endpoint = f"/cgi-bin/MANGA/api.cgi?{query_string}"
            
        return endpoint
    
    async def _make_api_request(self, func: str, public_api: bool = False, method: str = "GET", data: Optional[Dict] = None, **kwargs) -> Dict:
        """Make an API request with proper URL formatting, authentication, and logging.
        
        Args:
            func: The API function to call (e.g., 'status.client' or 'status.traffic')
            public_api: If True, use the /api/ style endpoint, otherwise use the cgi-bin style
            method: HTTP method to use (default: GET)
            data: Optional JSON data for POST requests
            **kwargs: Additional URL parameters to include
            
        Returns:
            Dict: The unmodified JSON response from the API
        """
        # Ensure we're authenticated
        if not await self.ensure_connected():
            _LOGGER.error("Failed to connect to Peplink router")
            raise Exception("Not connected to Peplink router")
            
        # Format the URL
        endpoint = await self._format_api_url(func, public_api=public_api, **kwargs)
        
        # Perform the API request
        _LOGGER.debug("Requesting data from %s", endpoint)
        response = await self._api_request(endpoint, method=method, data=data)
        
        # Log the response
        _LOGGER.debug("Raw data from router: %s", response)
        
        # Return the unmodified JSON response
        return response

    async def get_wan_status(self) -> Dict[str, Any]:
        """
        Retrieve WAN status for all WAN links.
        
        Returns:
            dict: Dictionary containing WAN status information
                 Format: {
                     "connection": [
                         {
                             "id": str,           # WAN interface ID
                             "name": str,         # WAN interface name
                             "status": str,       # Connection status (e.g., "connected", "disconnected")
                             "type": str,         # WAN connection type
                             "ipAddress": str,    # IP address if connected
                             "gateway": str,      # Gateway IP address
                             "dns": list,         # List of DNS servers
                             "mac": str,          # MAC address of the WAN interface
                             # Additional fields may be present depending on the router model
                         },
                         # Additional WAN connections...
                     ]
                 }
        """
        try:
            response = await self._make_api_request("status.wan", public_api=True)
            
            # Check for error response
            if "stat" in response and response["stat"] == "fail":
                _LOGGER.error("API error: %s (code: %s)", 
                             response.get("message", "Unknown error"), 
                             response.get("code", "Unknown"))
                return {"connection": []}
                
            # Handle different response formats
            if "stat" in response and response["stat"] == "ok":
                if "response" in response:
                    response_data = response["response"]
                    
                    # Extract WAN interfaces (numeric keys)
                    wans = []
                    for key, value in response_data.items():
                        # Skip non-WAN keys like 'order' or 'supportGatewayProxy'
                        if isinstance(key, str) and key.isdigit():
                            # Add the WAN ID to each WAN object
                            value["id"] = key
                            value["name"] = value.get("name", f"WAN {key}")
                            value["status"] = value.get("status", "unknown")
                            wans.append(value)
                    
                    _LOGGER.debug("Processed %d WAN interfaces", len(wans))
                    return {"connection": wans}
            
            # Handle alternative format where WAN data is directly in the response
            if "connection" in response:
                _LOGGER.debug("Found 'connection' key in WAN data")
                return response
            
            _LOGGER.warning("Unexpected WAN data format: %s", response)
            return {"connection": []}
                    
        except aiohttp.ClientError as e:
            _LOGGER.error("Error retrieving WAN status: %s", e)
            return {"connection": []}
        except json.JSONDecodeError:
            _LOGGER.error("Unexpected response format for WAN status")
            return {"connection": []}
    
    async def get_clients(self) -> Dict[str, Any]:
        """
        Retrieve information about all connected clients.
        
        Returns:
            dict: Dictionary containing client information
                 Format: {
                     "client": [
                         {
                             "mac": str,           # MAC address of the client
                             "name": str,          # Client name or hostname
                             "ip": str,            # IP address assigned to the client
                             "rssi": int,          # Signal strength (for wireless clients)
                             "connected": bool,    # Always True for connected clients
                             "interface": str,     # Network interface the client is connected to
                             "vlan": str,          # VLAN the client is connected to (if applicable)
                             "ssid": str,          # Wireless SSID (for wireless clients)
                             # Additional fields may be present depending on the router model
                         },
                         # Additional clients...
                     ]
                 }
        """
        try:
            response = await self._make_api_request("status.client", public_api=True)
            
            # Check for error response
            if "stat" in response and response["stat"] == "fail":
                _LOGGER.error("API error: %s (code: %s)", 
                             response.get("message", "Unknown error"), 
                             response.get("code", "Unknown"))
                return {"client": []}
                
            # Handle different response formats
            if "stat" in response and response["stat"] == "ok":
                if "response" in response:
                    if "list" in response["response"]:
                        clients = response["response"]["list"]
                        for client in clients:
                            # Ensure each client has the required fields
                            client["connected"] = True  # If it's in the list, it's connected
                            client["mac"] = client.get("mac", "unknown")
                            client["name"] = client.get("name", client.get("hostname", "Unknown Device"))
                        
                        _LOGGER.debug("Processed %d clients", len(clients))
                        return {"client": clients}
            
            # Handle alternative format where client data is directly in the response
            if "client" in response:
                _LOGGER.debug("Found 'client' key in client data")
                return response
            
            _LOGGER.warning("Unexpected client data format: %s", response)
            return {"client": []}
                    
        except aiohttp.ClientError as e:
            _LOGGER.error("Error retrieving client information: %s", e)
            return {"client": []}
        except json.JSONDecodeError:
            _LOGGER.error("Unexpected response format for client information")
            return {"client": []}

    async def get_system_info(self) -> Dict[str, Any]:
        """
        Retrieve combined system information from the router including device info, thermal sensors, and fan speeds.
        
        Returns:
            dict: Dictionary containing combined system information
                 Format: {
                     "device_info": {
                         "serial_number": str,      # Router serial number
                         "name": str,               # Router hostname
                         "model": str,              # Router model
                         "product_code": str,       # Product code
                         "hardware_revision": str,  # Hardware revision
                         "firmware_version": str,   # Firmware version
                         "host": str,               # Host address
                         "pepvpn_version": str      # PepVPN version
                     },
                     "thermal_sensors": {
                         "sensors": [
                             {
                                 "name": str,        # Sensor name
                                 "temperature": float, # Current temperature
                                 "unit": str,        # Temperature unit (C)
                                 "min": float,       # Minimum temperature
                                 "max": float,       # Maximum temperature
                                 "threshold": float  # Temperature threshold
                             }
                         ]
                     },
                     "fan_speeds": {
                         "fans": [
                             {
                                 "name": str,        # Fan name
                                 "speed": int,       # Current speed
                                 "unit": str,        # Speed unit (RPM)
                                 "max_speed": int,   # Maximum speed
                                 "percentage": float # Speed as percentage of maximum
                             }
                         ]
                     },
                     "system_time": {
                         "time_string": str,        # Formatted time string
                         "timestamp": int,          # UNIX timestamp
                         "timezone": str            # Timezone
                     }
                 }
        """
        try:
            # Combined info types in a single request
            response = await self._make_api_request("status.system.info", public_api=False, infoType="device%20systemTime%20thermalSensor%20fanSpeed")
                
            result = {
                "device_info": {},
                "thermal_sensors": {"sensors": []},
                "fan_speeds": {"fans": []},
                "system_time": {}
            }
                
            # Process the response
            if response.get("stat") == "ok" and "response" in response:
                # Process device information
                device_info = response["response"].get("device", {})
                if device_info:
                    result["device_info"] = {
                        "serial_number": device_info.get("serialNumber", ""),
                        "name": device_info.get("name", ""),
                        "model": device_info.get("model", ""),
                        "product_code": device_info.get("productCode", ""),
                        "hardware_revision": device_info.get("hardwareRevision", ""),
                        "firmware_version": device_info.get("firmwareVersion", ""),
                        "host": device_info.get("host", ""),
                        "pepvpn_version": device_info.get("pepvpnVersion", "")
                    }
                
                # Process thermal sensor information
                sensors = []
                for sensor in response["response"].get("thermalSensor", []):
                    sensors.append({
                        "name": "System",  # Only one sensor per device
                        "temperature": float(sensor.get("temperature", 0)),
                        "unit": "C",
                        "min": float(sensor.get("min", -30)),
                        "max": float(sensor.get("max", 110)),
                        "threshold": float(sensor.get("threshold", 30))
                    })
                result["thermal_sensors"] = {"sensors": sensors}
                
                # Process fan speed information
                fans = []
                for i, fan in enumerate(response["response"].get("fanSpeed", []), 1):
                    if fan.get("active", False):
                        fans.append({
                            "name": f"Fan {i}",
                            "speed": int(fan.get("value", 0)),
                            "unit": "RPM",
                            "max_speed": int(fan.get("total", 17000)),
                            "percentage": float(fan.get("percentage", 0))
                        })
                result["fan_speeds"] = {"fans": fans}
                
                # Process system time information
                system_time = response["response"].get("systemTime", {})
                if system_time:
                    result["system_time"] = {
                        "time_string": system_time.get("string", ""),
                        "timestamp": system_time.get("timestamp", 0),
                        "timezone": system_time.get("timezone", "")
                    }
                
                return result
            else:
                _LOGGER.warning("Unexpected combined system information format: %s", response)
                return result
                    
        except Exception as e:
            _LOGGER.error("Error fetching combined system information: %s", e)
            return {
                "device_info": {},
                "thermal_sensors": {"sensors": []},
                "fan_speeds": {"fans": []},
                "system_time": {}
            }

    async def get_thermal_sensors(self) -> Dict[str, Any]:
        """
        Retrieve thermal sensor data from the router using undocumented API.
        
        Returns:
            dict: Dictionary containing thermal sensor information
                 Format: {
                     "sensors": [
                         {
                             "name": str,          # Sensor name
                             "temperature": float,  # Current temperature
                             "unit": str,           # Temperature unit (C)
                             "min": float,          # Minimum temperature
                             "max": float,          # Maximum temperature
                             "threshold": float     # Temperature threshold
                         }
                     ]
                 }
        """
        # Try to get data from the combined system info call for efficiency
        try:
            system_info = await self.get_system_info()
            if system_info and system_info.get("thermal_sensors", {}).get("sensors"):
                return system_info["thermal_sensors"]
        except Exception as e:
            _LOGGER.warning("Error getting thermal sensors from combined call, falling back to dedicated call: %s", e)
        
        # Fallback to the original method if combined call fails
        try:
            response = await self._make_api_request("status.system.info", public_api=False, infoType="thermalSensor")
                
            # Process the response
            if response.get("stat") == "ok" and "response" in response:
                sensors = []
                for sensor in response["response"].get("thermalSensor", []):
                    sensors.append({
                        "name": "System",  # Only one sensor per device
                        "temperature": float(sensor.get("temperature", 0)),
                        "unit": "C",
                        "min": float(sensor.get("min", -30)),
                        "max": float(sensor.get("max", 110)),
                        "threshold": float(sensor.get("threshold", 30))
                    })
                return {"sensors": sensors}
            else:
                _LOGGER.warning("Unexpected thermal sensor data format: %s", response)
                return {"sensors": []}
                    
        except Exception as e:
            _LOGGER.error("Error fetching thermal sensor data: %s", e)
            return {"sensors": []}

    async def get_fan_speeds(self) -> Dict[str, Any]:
        """
        Retrieve fan speed data from the router using undocumented API.
        
        Returns:
            dict: Dictionary containing fan speed information
                 Format: {
                     "fans": [
                         {
                             "name": str,          # Fan name
                             "speed": int,          # Current speed
                             "unit": str,           # Speed unit (RPM)
                             "max_speed": int,      # Maximum speed
                             "percentage": float    # Speed as percentage of maximum
                         }
                     ]
                 }
        """
        # Try to get data from the combined system info call for efficiency
        try:
            system_info = await self.get_system_info()
            if system_info and system_info.get("fan_speeds", {}).get("fans"):
                return system_info["fan_speeds"]
        except Exception as e:
            _LOGGER.warning("Error getting fan speeds from combined call, falling back to dedicated call: %s", e)
            
        # Fallback to the original method if combined call fails
        try:
            response = await self._make_api_request("status.system.info", public_api=False, infoType="fanSpeed")
                
            # Process the response
            if response.get("stat") == "ok" and "response" in response:
                fans = []
                for i, fan in enumerate(response["response"].get("fanSpeed", []), 1):
                    if fan.get("active", False):
                        fans.append({
                            "name": f"Fan {i}",
                            "speed": int(fan.get("value", 0)),
                            "unit": "RPM",
                            "max_speed": int(fan.get("total", 17000)),
                            "percentage": float(fan.get("percentage", 0))
                        })
                return {"fans": fans}
            else:
                _LOGGER.warning("Unexpected fan speed data format: %s", response)
                return {"fans": []}
                    
        except Exception as e:
            _LOGGER.error("Error fetching fan speed data: %s", e)
            return {"fans": []}

    async def get_device_info(self) -> Dict[str, Any]:
        """
        Retrieve device information from the router.
        
        Returns:
            dict: Dictionary containing device information
                 Format: {
                     "device_info": {
                         "serial_number": str,      # Router serial number
                         "name": str,               # Router hostname
                         "model": str,              # Router model
                         "product_code": str,       # Product code
                         "hardware_revision": str,  # Hardware revision
                         "firmware_version": str,   # Firmware version
                         "host": str,               # Host address
                         "pepvpn_version": str      # PepVPN version
                     }
                 }
        """
        # Try to get data from the combined system info call for efficiency
        try:
            system_info = await self.get_system_info()
            if system_info and system_info.get("device_info"):
                return {"device_info": system_info["device_info"]}
        except Exception as e:
            _LOGGER.warning("Error getting device info from combined call, falling back to dedicated call: %s", e)
        
        # Fallback to the original method if combined call fails
        try:
            response = await self._make_api_request("status.system.info", public_api=False, infoType="device")
                
            # Process the response
            if response.get("stat") == "ok" and "response" in response:
                device_info = response["response"].get("device", {})
                
                if device_info:
                    info = {
                        "serial_number": device_info.get("serialNumber", ""),
                        "name": device_info.get("name", ""),
                        "model": device_info.get("model", ""),
                        "product_code": device_info.get("productCode", ""),
                        "hardware_revision": device_info.get("hardwareRevision", ""),
                        "firmware_version": device_info.get("firmwareVersion", ""),
                        "host": device_info.get("host", ""),
                        "pepvpn_version": device_info.get("pepvpnVersion", "")
                    }
                    return {"device_info": info}
            
            _LOGGER.warning("Unexpected device information format: %s", response)
            return {"device_info": {}}
                    
        except Exception as e:
            _LOGGER.error("Error fetching device information: %s", e)
            return {"device_info": {}}

    async def get_traffic_stats(self) -> Dict[str, Any]:
        """
        Retrieve traffic statistics from the router using undocumented API.
        
        Returns:
            dict: Dictionary containing traffic statistics for each WAN interface
                 Format: {
                     "stats": [
                         {
                             "wan_id": str,         # WAN interface ID
                             "name": str,           # WAN interface name
                             "rx_bytes": int,       # Received bytes
                             "tx_bytes": int,       # Transmitted bytes
                             "rx_rate": int,        # Current receive rate
                             "tx_rate": int,        # Current transmit rate
                             "unit": str            # Unit (bytes)
                         }
                     ]
                 }
        """
        # Get WAN status first to get names and IDs for interfaces
        try:
            wan_status = await self.get_wan_status()
            wan_interfaces = {}
            
            if "connection" in wan_status:
                for conn in wan_status["connection"]:
                    if "id" in conn and "name" in conn:
                        wan_interfaces[conn["id"]] = conn["name"]
            
            _LOGGER.debug("Found WAN interfaces: %s", wan_interfaces)
            
            # Try different API endpoints for traffic statistics
            # 1. First try "status.traffic" endpoint
            try:
                response = await self._make_api_request("status.traffic", public_api=False)
                
                if response.get("stat") == "ok" and "response" in response:
                    stats_data = response["response"]
                    _LOGGER.debug("Received traffic statistics from status.traffic: %s", stats_data)
                    
                    wan_stats = []
                    for wan_id, wan_data in stats_data.items():
                        # Skip non-WAN keys
                        if not isinstance(wan_id, str) or not wan_id.isdigit():
                            continue
                        
                        # Extract relevant statistics
                        stats_entry = {
                            "wan_id": wan_id,
                            "name": wan_data.get("name", wan_interfaces.get(wan_id, f"WAN {wan_id}")),
                            "rx_bytes": wan_data.get("rx", 0),
                            "tx_bytes": wan_data.get("tx", 0),
                            "rx_rate": wan_data.get("rx_rate", 0),
                            "tx_rate": wan_data.get("tx_rate", 0),
                            "unit": "bytes"
                        }
                        wan_stats.append(stats_entry)
                    
                    if wan_stats:
                        _LOGGER.debug("Processed traffic stats for %d WAN interfaces", len(wan_stats))
                        return {"stats": wan_stats}
            except Exception as e:
                _LOGGER.debug("Error from status.traffic endpoint: %s", e)
            
            # 2. Try "status.wan.statistics" endpoint (different naming in some firmware versions)
            try:
                response = await self._make_api_request("status.wan.statistics", public_api=False)
                
                if response.get("stat") == "ok" and "response" in response:
                    stats_data = response["response"]
                    _LOGGER.debug("Received data from status.wan.statistics: %s", stats_data)
                    
                    wan_stats = []
                    # Handle different possible data formats
                    if isinstance(stats_data, dict):
                        for wan_id, wan_data in stats_data.items():
                            if not isinstance(wan_id, str) or not wan_id.isdigit():
                                continue
                                
                            stats_entry = {
                                "wan_id": wan_id,
                                "name": wan_interfaces.get(wan_id, f"WAN {wan_id}"),
                                "rx_bytes": wan_data.get("rx_bytes", wan_data.get("rx", 0)),
                                "tx_bytes": wan_data.get("tx_bytes", wan_data.get("tx", 0)),
                                "rx_rate": wan_data.get("rx_rate", 0),
                                "tx_rate": wan_data.get("tx_rate", 0),
                                "unit": "bytes"
                            }
                            wan_stats.append(stats_entry)
                    
                    if wan_stats:
                        _LOGGER.debug("Processed traffic stats from status.wan.statistics: %d interfaces", len(wan_stats))
                        return {"stats": wan_stats}
            except Exception as e:
                _LOGGER.debug("Error from status.wan.statistics endpoint: %s", e)
            
            # 3. Create placeholder entries for Home Assistant
            if wan_interfaces:
                _LOGGER.warning("No traffic data available from API endpoints. Creating placeholder data for interfaces.")
                wan_stats = []
                for wan_id, wan_name in wan_interfaces.items():
                    stats_entry = {
                        "wan_id": wan_id,
                        "name": wan_name,
                        "rx_bytes": 0,
                        "tx_bytes": 0,
                        "rx_rate": 0,
                        "tx_rate": 0,
                        "unit": "bytes"
                    }
                    wan_stats.append(stats_entry)
                
                _LOGGER.debug("Created placeholder traffic stats for %d WAN interfaces", len(wan_stats))
                return {"stats": wan_stats}
            
            # If all methods fail, return empty stats
            _LOGGER.warning("Could not retrieve traffic statistics from any endpoint")
            return {"stats": []}
            
        except Exception as e:
            _LOGGER.error("Error retrieving traffic statistics: %s", e)
            return {"stats": []}

    async def get_location(self) -> Dict[str, Any]:
        """
        Retrieve location information from the router using GPS data.
        
        Returns:
            dict: Dictionary containing location information
                Format: {
                    "gps": bool,                  # Whether GPS is enabled
                    "type": str,                  # GPS type
                    "location": {
                        "timeElapsed": int,       # Time elapsed since last update
                        "timestamp": int,         # UNIX timestamp
                        "latitude": float,        # Latitude in degrees
                        "longitude": float,       # Longitude in degrees
                        "altitude": float,        # Altitude in meters
                        "speed": float,           # Speed in km/h
                        "heading": float,         # Heading in degrees
                        "accuracy": float,        # Accuracy in meters
                        "pdop": float,            # Position Dilution of Precision
                        "hdop": float,            # Horizontal Dilution of Precision
                        "vdop": float             # Vertical Dilution of Precision
                    }
                }
        """
        try:
            response = await self._make_api_request("info.location", public_api=False)
            
            if "stat" in response and response["stat"] == "ok" and "response" in response:
                location_data = response["response"]
                _LOGGER.debug("Received location data: %s", location_data)
                
                # Check if GPS is explicitly set to False
                if location_data.get("gps") is False:
                    _LOGGER.debug("Router does not have GPS capability")
                    return {"gps": False, "type": "Unknown", "location": {}}
                
                # Process the location data to ensure consistent attribute names
                if "location" in location_data and location_data.get("gps", False):
                    loc = location_data["location"]
                    
                    # Calculate GPS accuracy from horizontal dilution of precision if available
                    if "hdop" in loc and loc.get("hdop") is not None:
                        # GPS accuracy is typically estimated as HDOP * base_precision
                        # Using 5 meters as the base precision
                        loc["accuracy"] = float(loc["hdop"]) * 5.0
                    
                    # Ensure heading is present if not available
                    if "heading" not in loc:
                        # Default heading if not available
                        loc["heading"] = None
                
                return location_data
            
            _LOGGER.warning("Unexpected location data format: %s", response)
            return {"gps": False, "type": "Unknown", "location": {}}
            
        except Exception as e:
            _LOGGER.error("Error retrieving location information: %s", e)
            return {"gps": False, "type": "Unknown", "location": {}}
            
    async def close(self) -> None:
        """Close the session if we created it."""
        if self._own_session and self._session is not None:
            await self._session.close()
            self._session = None
            self._own_session = False
            self._connected = False