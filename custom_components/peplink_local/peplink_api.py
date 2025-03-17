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

    async def get_wan_status(self) -> Dict[str, Any]:
        """
        Retrieve WAN status for all WAN links.
        
        Returns:
            dict: Dictionary containing WAN status information
        """
        if not await self.ensure_connected():
            _LOGGER.error("Failed to connect to Peplink router")
            return {"connection": []}
        
        session = await self._get_session()
        wan_url = urljoin(self.base_url, "/api/status.wan")
        
        try:
            _LOGGER.debug("Requesting WAN status from %s", wan_url)
            response = await self._api_request(wan_url)
            
            _LOGGER.debug("Raw WAN data from router: %s", response)
                
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
        """
        if not await self.ensure_connected():
            _LOGGER.error("Failed to connect to Peplink router")
            return {"client": []}
        
        session = await self._get_session()
        clients_url = urljoin(self.base_url, "/api/status.client")
        
        try:
            _LOGGER.debug("Requesting client status from %s", clients_url)
            response = await self._api_request(clients_url)
            
            _LOGGER.debug("Raw client data from router: %s", response)
                
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
                     "device_info": {...},
                     "thermal_sensors": {...},
                     "fan_speeds": {...},
                     "system_time": {...}
                 }
        """
        if not await self.ensure_connected():
            _LOGGER.error("Failed to connect to Peplink router")
            return {
                "device_info": {},
                "thermal_sensors": {"sensors": []},
                "fan_speeds": {"fans": []},
                "system_time": {}
            }
        
        session = await self._get_session()
        # Combined info types in a single request
        url = urljoin(self.base_url, f"/cgi-bin/MANGA/api.cgi?func=status.system.info&infoType=device%20systemTime%20thermalSensor%20fanSpeed&_={int(time.time() * 1000)}")
        
        try:
            _LOGGER.debug("Requesting combined system information from %s", url)
            response = await self._api_request(url)
            
            _LOGGER.debug("Raw combined system information from router: %s", response)
            
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
                 Format: {"sensors": [{"name": str, "temperature": float, "unit": str, "min": float, "max": float, "threshold": float}]}
        """
        # Try to get data from the combined system info call for efficiency
        try:
            system_info = await self.get_system_info()
            if system_info and system_info.get("thermal_sensors", {}).get("sensors"):
                return system_info["thermal_sensors"]
        except Exception as e:
            _LOGGER.warning("Error getting thermal sensors from combined call, falling back to dedicated call: %s", e)
        
        # Fallback to the original method if combined call fails
        if not await self.ensure_connected():
            _LOGGER.error("Failed to connect to Peplink router")
            return {"sensors": []}
        
        session = await self._get_session()
        url = urljoin(self.base_url, f"/cgi-bin/MANGA/api.cgi?func=status.system.info&infoType=thermalSensor&_={int(time.time() * 1000)}")
        
        try:
            _LOGGER.debug("Requesting thermal sensor data from %s", url)
            response = await self._api_request(url)
            
            _LOGGER.debug("Raw thermal sensor data from router: %s", response)
                
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
                 Format: {"fans": [{"name": str, "speed": int, "unit": str, "max_speed": int, "percentage": float}]}
        """
        # Try to get data from the combined system info call for efficiency
        try:
            system_info = await self.get_system_info()
            if system_info and system_info.get("fan_speeds", {}).get("fans"):
                return system_info["fan_speeds"]
        except Exception as e:
            _LOGGER.warning("Error getting fan speeds from combined call, falling back to dedicated call: %s", e)
            
        # Fallback to the original method if combined call fails
        if not await self.ensure_connected():
            _LOGGER.error("Failed to connect to Peplink router")
            return {"fans": []}
        
        session = await self._get_session()
        url = urljoin(self.base_url, f"/cgi-bin/MANGA/api.cgi?func=status.system.info&infoType=fanSpeed&_={int(time.time() * 1000)}")
        
        try:
            _LOGGER.debug("Requesting fan speed data from %s", url)
            response = await self._api_request(url)
            
            _LOGGER.debug("Raw fan speed data from router: %s", response)
                
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
                         "serial_number": str,
                         "name": str,
                         "model": str,
                         "product_code": str,
                         "hardware_revision": str,
                         "firmware_version": str,
                         "host": str,
                         "pepvpn_version": str
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
        if not await self.ensure_connected():
            _LOGGER.error("Failed to connect to Peplink router")
            return {"device_info": {}}
        
        session = await self._get_session()
        url = urljoin(self.base_url, f"/cgi-bin/MANGA/api.cgi?func=status.system.info&infoType=device&_={int(time.time() * 1000)}")
        
        try:
            _LOGGER.debug("Requesting device information from %s", url)
            response = await self._api_request(url)
            
            _LOGGER.debug("Raw device information from router: %s", response)
                
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
                     "stats": [{
                         "wan_id": str,
                         "name": str,
                         "rx_bytes": int,
                         "tx_bytes": int,
                         "rx_rate": int,
                         "tx_rate": int,
                         "unit": str
                     }]
                 }
        """
        if not await self.ensure_connected():
            _LOGGER.error("Failed to connect to Peplink router")
            return {"stats": []}
        
        session = await self._get_session()
        url = urljoin(self.base_url, f"/cgi-bin/MANGA/api.cgi?func=status.traffic&_={int(time.time() * 1000)}")
        
        try:
            _LOGGER.debug("Requesting traffic statistics from %s", url)
            response = await self._api_request(url)
            
            _LOGGER.debug("Raw traffic statistics from router: %s", response)
                
            # Process the response
            if response.get("stat") == "ok" and "response" in response:
                stats = []
                traffic_data = response["response"].get("traffic", {})
                bandwidth_data = response["response"].get("bandwidth", {})
                
                # Get the list of WAN IDs in order
                wan_ids = traffic_data.get("order", [])
                
                for wan_id in wan_ids:
                    wan_id_str = str(wan_id)
                    traffic = traffic_data.get(wan_id_str, {})
                    bandwidth = bandwidth_data.get(wan_id_str, {})
                    
                    if traffic and bandwidth:
                        stats.append({
                            "wan_id": wan_id_str,
                            "name": traffic.get("name", f"WAN {wan_id}"),
                            "rx_bytes": int(traffic.get("overall", {}).get("download", 0)) * 1024 * 1024,  # Convert MB to bytes
                            "tx_bytes": int(traffic.get("overall", {}).get("upload", 0)) * 1024 * 1024,    # Convert MB to bytes
                            "rx_rate": int(bandwidth.get("overall", {}).get("download", 0)) * 1024,        # Convert kbps to bps
                            "tx_rate": int(bandwidth.get("overall", {}).get("upload", 0)) * 1024,          # Convert kbps to bps
                            "unit": "bytes"
                        })
                
                return {"stats": stats}
            else:
                _LOGGER.warning("Unexpected traffic statistics format: %s", response)
                return {"stats": []}
                    
        except Exception as e:
            _LOGGER.error("Error fetching traffic statistics: %s", e)
            return {"stats": []}

    async def close(self) -> None:
        """Close the session if we created it."""
        if self._own_session and self._session is not None:
            await self._session.close()
            self._session = None
            self._own_session = False
            self._connected = False