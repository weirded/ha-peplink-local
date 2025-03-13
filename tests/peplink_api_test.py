"""Standalone version of the Peplink API client for testing."""
import aiohttp
import asyncio
import json
import logging
import ssl
from typing import Any, Dict, List, Optional

_LOGGER = logging.getLogger(__name__)

class PeplinkAPI:
    """API client for Peplink routers."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        session: Optional[aiohttp.ClientSession] = None,
        verify_ssl: bool = True,
    ) -> None:
        """Initialize the API client."""
        self.host = host if host.startswith(("http://", "https://")) else f"https://{host}"
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self._session = session
        self._own_session = False
        self.token = None

    async def connect(self) -> bool:
        """Connect to the Peplink router and get an authentication token."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._own_session = True

        # Create SSL context if verify_ssl is False
        if not self.verify_ssl:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self._session = aiohttp.ClientSession(connector=connector)
            self._own_session = True

        try:
            url = f"{self.host}/api/login"
            data = {
                "username": self.username,
                "password": self.password
            }

            async with self._session.post(url, json=data) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to connect to Peplink router: %s", response.status)
                    return False

                result = await response.json()
                self.token = result.get("token")
                return bool(self.token)

        except Exception as err:
            _LOGGER.error("Error connecting to Peplink router: %s", err)
            return False

    async def _api_wrapper(
        self, method: str, url: str, data: dict = None
    ) -> Optional[Dict[str, Any]]:
        """Wrap API calls with error handling and authentication."""
        if not self.token:
            _LOGGER.error("No authentication token available")
            return None

        headers = {"Authorization": f"Token {self.token}"}

        try:
            async with self._session.request(
                method, f"{self.host}{url}", headers=headers, json=data
            ) as response:
                if response.status == 401:
                    _LOGGER.error("Authentication failed")
                    return None
                response.raise_for_status()
                return await response.json()

        except aiohttp.ClientResponseError as err:
            _LOGGER.error("HTTP error occurred: %s", err)
            return None
        except Exception as err:
            _LOGGER.error("Error occurred: %s", err)
            return None

    async def get_wan_status(self) -> Optional[Dict[str, Any]]:
        """Get WAN connection status."""
        return await self._api_wrapper("GET", "/api/status.wan.connection")

    async def get_clients(self) -> Optional[Dict[str, Any]]:
        """Get connected client information."""
        return await self._api_wrapper("GET", "/api/status.client")

    async def get_thermal_sensors(self) -> Optional[Dict[str, Any]]:
        """Get thermal sensor data."""
        return await self._api_wrapper("GET", "/api/status.thermal")

    async def get_fan_speeds(self) -> Optional[Dict[str, Any]]:
        """Get fan speed data."""
        return await self._api_wrapper("GET", "/api/status.fan")

    async def get_traffic_stats(self) -> Optional[Dict[str, Any]]:
        """Get traffic statistics."""
        return await self._api_wrapper("GET", "/api/status.traffic")

    async def close(self) -> None:
        """Close the API client."""
        if self._session and self._own_session:
            await self._session.close()
            self._session = None
