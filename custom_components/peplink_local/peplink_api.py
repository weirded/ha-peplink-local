#!/usr/bin/env python3
"""
Peplink API Client - Async API class for interacting with the Peplink router API

This module provides the PeplinkAPI class that connects to a Peplink router's local API,
authenticates, and retrieves information about WAN status and connected clients.
"""
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
        router_ip: str, 
        username: str, 
        password: str, 
        session: Optional[aiohttp.ClientSession] = None,
        verify_ssl: bool = True
    ):
        """
        Initialize the Peplink API client.
        
        Args:
            router_ip (str): IP address of the Peplink router
            username (str): Username for authentication
            password (str): Password for authentication
            session (aiohttp.ClientSession, optional): Existing aiohttp session
            verify_ssl (bool): Whether to verify SSL certificates (used by caller)
        """
        self.base_url = f"https://{router_ip}"
        self.username = username
        self.password = password
        self._session = session
        self.verify_ssl = verify_ssl  # Kept for compatibility, but SSL is handled by the session
        self._connected = False
        self._own_session = False
        self._cookie_jar = None
        self._auth_cookie = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get the current session or create a new one."""
        if self._session is None:
            # Create a session with the appropriate SSL settings
            if not self.verify_ssl:
                # Create SSL context in a non-blocking way
                loop = asyncio.get_running_loop()
                ssl_context = await loop.run_in_executor(
                    None, 
                    partial(_create_insecure_ssl_context)
                )
                
                # Create a connector with the SSL context
                connector = aiohttp.TCPConnector(ssl=ssl_context)
                
                # Create a cookie jar that accepts all cookies
                self._cookie_jar = aiohttp.CookieJar(unsafe=True)
                
                # Create a session with the cookie jar and connector
                self._session = aiohttp.ClientSession(
                    connector=connector, 
                    cookie_jar=self._cookie_jar
                )
            else:
                # Create a session with default SSL settings but with a cookie jar
                self._cookie_jar = aiohttp.CookieJar()
                self._session = aiohttp.ClientSession(cookie_jar=self._cookie_jar)
                
            self._own_session = True
            
        # Add the authentication cookie to all requests
        if self._auth_cookie:
            self._session.cookie_jar.update_cookies({'bauth': self._auth_cookie})

        return self._session

    async def connect(self) -> bool:
        """
        Establish a connection to the Peplink router and authenticate.
        
        Returns:
            bool: True if connection and authentication were successful
        """
        if self._connected:
            return True
            
        session = await self._get_session()
        
        # Get the web login challenge
        challenge_url = urljoin(self.base_url, "/api/login")
        try:
            _LOGGER.debug("Getting login challenge from %s", challenge_url)
            async with session.get(challenge_url) as response:
                response.raise_for_status()
                challenge_data = await response.json()
                _LOGGER.debug("Received challenge: %s", challenge_data)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error connecting to Peplink router: %s", e)
            return False
        except json.JSONDecodeError:
            _LOGGER.error("Unexpected response format from the router")
            return False
        
        # Perform the login
        login_data = {
            "username": self.username,
            "password": self.password,
            "challenge": challenge_data.get("challenge", "")
        }
        
        try:
            _LOGGER.debug("Sending login request with data: %s", {**login_data, 'password': '***'})
            async with session.post(challenge_url, json=login_data) as response:
                response.raise_for_status()
                login_result = await response.json()
                _LOGGER.debug("Login response: %s", login_result)
                
                # Check for success in multiple formats
                if not (login_result.get("success", False) or login_result.get("stat") == "ok"):
                    error_msg = login_result.get('message', 'Unknown error')
                    _LOGGER.error("Login failed: %s", error_msg)
                    return False
                
                # Store any cookies or tokens returned by the server
                if 'token' in login_result:
                    _LOGGER.debug("Setting auth token for future requests")
                    session.headers.update({"Authorization": f"Bearer {login_result['token']}"})
                
                # Check if cookies were set
                cookies = session.cookie_jar.filter_cookies(response.url)
                _LOGGER.debug("Cookies after login: %s", cookies)
                
                # Some Peplink routers use cookies for authentication
                if not cookies:
                    _LOGGER.debug("No cookies set, checking for session ID in response")
                    # Check if there's a session ID in the response
                    if 'session_id' in login_result:
                        cookie = {'session_id': login_result['session_id']}
                        _LOGGER.debug("Setting session cookie: %s", cookie)
                        session.cookie_jar.update_cookies(cookie, response.url)
                    
                # Store the authentication cookie
                self._auth_cookie = cookies.get('bauth', None)
                    
        except aiohttp.ClientError as e:
            _LOGGER.error("Error during login: %s", e)
            return False
        except json.JSONDecodeError:
            _LOGGER.error("Unexpected response format from the router")
            return False
        
        # Verify that we can access protected endpoints
        try:
            _LOGGER.debug("Verifying authentication by accessing a protected endpoint")
            test_url = urljoin(self.base_url, "/api/status.system")
            async with session.get(test_url) as response:
                if response.status == 401:
                    _LOGGER.error("Authentication verification failed: Unauthorized")
                    return False
                response.raise_for_status()
                test_data = await response.json()
                _LOGGER.debug("Authentication verification successful: %s", test_data)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error verifying authentication: %s", e)
            return False
        except json.JSONDecodeError:
            _LOGGER.error("Unexpected response format during authentication verification")
            return False
        
        self._connected = True
        return True
    
    async def ensure_connected(self) -> bool:
        """Ensure that a connection has been established."""
        if not self._connected:
            return await self.connect()
        return True
    
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
            async with session.get(wan_url) as response:
                # If we get a 401, try to reconnect once
                if response.status == 401:
                    _LOGGER.warning("Authentication expired, attempting to reconnect")
                    self._connected = False
                    if not await self.connect():
                        _LOGGER.error("Failed to reconnect to Peplink router")
                        return {"connection": []}
                    
                    # Retry the request with the new session
                    session = await self._get_session()
                    async with session.get(wan_url) as retry_response:
                        retry_response.raise_for_status()
                        wan_data = await retry_response.json()
                else:
                    response.raise_for_status()
                    wan_data = await response.json()
                
                _LOGGER.debug("Raw WAN data from router: %s", wan_data)
                
                # Check for error response
                if "stat" in wan_data and wan_data["stat"] == "fail":
                    _LOGGER.error("API error: %s (code: %s)", 
                                 wan_data.get("message", "Unknown error"), 
                                 wan_data.get("code", "Unknown"))
                    return {"connection": []}
                
                # Handle different response formats
                if "stat" in wan_data and wan_data["stat"] == "ok":
                    if "response" in wan_data:
                        response_data = wan_data["response"]
                        
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
                if "connection" in wan_data:
                    _LOGGER.debug("Found 'connection' key in WAN data")
                    return wan_data
                
                _LOGGER.warning("Unexpected WAN data format: %s", wan_data)
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
            async with session.get(clients_url) as response:
                # If we get a 401, try to reconnect once
                if response.status == 401:
                    _LOGGER.warning("Authentication expired, attempting to reconnect")
                    self._connected = False
                    if not await self.connect():
                        _LOGGER.error("Failed to reconnect to Peplink router")
                        return {"client": []}
                    
                    # Retry the request with the new session
                    session = await self._get_session()
                    async with session.get(clients_url) as retry_response:
                        retry_response.raise_for_status()
                        clients_data = await retry_response.json()
                else:
                    response.raise_for_status()
                    clients_data = await response.json()
                
                _LOGGER.debug("Raw client data from router: %s", clients_data)
                
                # Check for error response
                if "stat" in clients_data and clients_data["stat"] == "fail":
                    _LOGGER.error("API error: %s (code: %s)", 
                                 clients_data.get("message", "Unknown error"), 
                                 clients_data.get("code", "Unknown"))
                    return {"client": []}
                
                # Handle different response formats
                if "stat" in clients_data and clients_data["stat"] == "ok":
                    if "response" in clients_data:
                        if "list" in clients_data["response"]:
                            clients = clients_data["response"]["list"]
                            for client in clients:
                                # Ensure each client has the required fields
                                client["connected"] = True  # If it's in the list, it's connected
                                client["mac"] = client.get("mac", "unknown")
                                client["name"] = client.get("name", client.get("hostname", "Unknown Device"))
                            
                            _LOGGER.debug("Processed %d clients", len(clients))
                            return {"client": clients}
                
                # Handle alternative format where client data is directly in the response
                if "client" in clients_data:
                    _LOGGER.debug("Found 'client' key in client data")
                    return clients_data
                
                _LOGGER.warning("Unexpected client data format: %s", clients_data)
                return {"client": []}
                    
        except aiohttp.ClientError as e:
            _LOGGER.error("Error retrieving client information: %s", e)
            return {"client": []}
        except json.JSONDecodeError:
            _LOGGER.error("Unexpected response format for client information")
            return {"client": []}
    
    async def get_thermal_sensors(self) -> Dict[str, Any]:
        """
        Retrieve thermal sensor data from the router using undocumented API.
        
        Returns:
            dict: Dictionary containing thermal sensor information
                 Format: {"sensors": [{"name": str, "temperature": float, "unit": str, "min": float, "max": float, "threshold": float}]}
        """
        if not await self.ensure_connected():
            _LOGGER.error("Failed to connect to Peplink router")
            return {"sensors": []}
        
        session = await self._get_session()
        url = urljoin(self.base_url, f"/cgi-bin/MANGA/api.cgi?func=status.system.info&infoType=thermalSensor&_={int(time.time() * 1000)}")
        
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                _LOGGER.debug("Raw thermal sensor data from router: %s", data)
                
                # Process the response
                if data.get("stat") == "ok" and "response" in data:
                    sensors = []
                    for sensor in data["response"].get("thermalSensor", []):
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
                    _LOGGER.warning("Unexpected thermal sensor data format: %s", data)
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
        if not await self.ensure_connected():
            _LOGGER.error("Failed to connect to Peplink router")
            return {"fans": []}
        
        session = await self._get_session()
        url = urljoin(self.base_url, f"/cgi-bin/MANGA/api.cgi?func=status.system.info&infoType=fanSpeed&_={int(time.time() * 1000)}")
        
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                _LOGGER.debug("Raw fan speed data from router: %s", data)
                
                # Process the response
                if data.get("stat") == "ok" and "response" in data:
                    fans = []
                    for i, fan in enumerate(data["response"].get("fanSpeed", []), 1):
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
                    _LOGGER.warning("Unexpected fan speed data format: %s", data)
                    return {"fans": []}
                    
        except Exception as e:
            _LOGGER.error("Error fetching fan speed data: %s", e)
            return {"fans": []}

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
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                _LOGGER.debug("Raw traffic statistics from router: %s", data)
                
                # Process the response
                if data.get("stat") == "ok" and "response" in data:
                    stats = []
                    traffic_data = data["response"].get("traffic", {})
                    bandwidth_data = data["response"].get("bandwidth", {})
                    
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
                    _LOGGER.warning("Unexpected traffic statistics format: %s", data)
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