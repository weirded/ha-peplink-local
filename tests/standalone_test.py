#!/usr/bin/env python3
"""
Test script for the Peplink API client.

This script tests the Peplink API client by connecting to a Peplink router
and fetching data from various endpoints.
"""

import asyncio
import json
import logging
import os
import sys
import ssl
from pathlib import Path
from urllib.parse import urljoin
import time
import aiohttp
import types

# Add the parent directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the API client directly from its file
sys.path.append(str(Path(__file__).parent.parent / "custom_components" / "peplink_local"))
from peplink_api import PeplinkAPI, _create_insecure_ssl_context  # isort:skip

# Import dotenv for loading environment variables
try:
    from dotenv import load_dotenv
except ImportError:
    print("dotenv package not found. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-dotenv"])
    from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
_LOGGER = logging.getLogger(__name__)

# Patch the _get_session method to fix SSL issues
async def patched_get_session(self) -> aiohttp.ClientSession:
    """Patched version of _get_session that works around SSL issues."""
    if not self._session:
        if self._verify_ssl:
            # Create a standard session
            self._session = aiohttp.ClientSession()
        else:
            # Create a session with SSL verification disabled
            ssl_context = _create_insecure_ssl_context()
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self._session = aiohttp.ClientSession(connector=connector)
            
        self._own_session = True
    
    return self._session

async def test_api(router_ip, username, password, verify_ssl=False):
    """Test the Peplink API by connecting and fetching data."""
    _LOGGER.info("Creating PeplinkAPI instance for %s", router_ip)
    api = PeplinkAPI(
        host=router_ip,
        username=username,
        password=password,
        verify_ssl=verify_ssl
    )
    
    # Patch the _get_session method to fix SSL issues
    api._get_session = types.MethodType(patched_get_session, api)
    
    # Create output directory if it doesn't exist
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    
    # Track test results
    test_results = {}
    
    try:
        # Test connection
        _LOGGER.info("Testing connection...")
        connected = await api.connect()
        if not connected:
            _LOGGER.error("Failed to connect to the Peplink router")
            return False
        
        _LOGGER.info("Successfully connected to the Peplink router")
        test_results["connection"] = "PASSED"
        
        # 1. Get combined system information (device info, thermal sensors, fan speeds, system time)
        _LOGGER.info("Fetching combined system information...")
        try:
            system_info = await api.get_system_info()
            _LOGGER.info("Combined system information: %s", json.dumps(system_info, indent=2))
            
            # Verify the system_info structure
            verify_system_info(system_info)
            
            # Save the complete system info to a file
            with open(output_dir / "system_info.json", "w") as f:
                json.dump(system_info, f, indent=2)
                
            test_results["system_info"] = "PASSED"
        except Exception as e:
            _LOGGER.error("Error during system_info test: %s", e)
            test_results["system_info"] = f"FAILED: {str(e)}"
            
        # 2. Get device information separately
        _LOGGER.info("Fetching device information separately...")
        try:
            device_info = await api.get_device_info()
            _LOGGER.info("Device information: %s", json.dumps(device_info, indent=2))
            
            # Verify the device_info structure
            verify_device_info(device_info)
            
            # Save to file
            with open(output_dir / "device_info.json", "w") as f:
                json.dump(device_info, f, indent=2)
                
            test_results["device_info"] = "PASSED"
        except Exception as e:
            _LOGGER.error("Error during device_info test: %s", e)
            test_results["device_info"] = f"FAILED: {str(e)}"
            
        # 3. Get thermal sensors data separately
        _LOGGER.info("Fetching thermal sensors data separately...")
        try:
            thermal_sensors = await api.get_thermal_sensors()
            _LOGGER.info("Thermal sensors data: %s", json.dumps(thermal_sensors, indent=2))
            
            # Verify the thermal sensors structure
            verify_thermal_sensors(thermal_sensors)
            
            # Save to file
            with open(output_dir / "thermal_sensors.json", "w") as f:
                json.dump(thermal_sensors, f, indent=2)
                
            test_results["thermal_sensors"] = "PASSED"
        except Exception as e:
            _LOGGER.error("Error during thermal_sensors test: %s", e)
            test_results["thermal_sensors"] = f"FAILED: {str(e)}"
            
        # 4. Get fan speeds data separately
        _LOGGER.info("Fetching fan speeds data separately...")
        try:
            fan_speeds = await api.get_fan_speeds()
            _LOGGER.info("Fan speeds data: %s", json.dumps(fan_speeds, indent=2))
            
            # Verify the fan speeds structure
            verify_fan_speeds(fan_speeds)
            
            # Save to file
            with open(output_dir / "fan_speeds.json", "w") as f:
                json.dump(fan_speeds, f, indent=2)
                
            test_results["fan_speeds"] = "PASSED"
        except Exception as e:
            _LOGGER.error("Error during fan_speeds test: %s", e)
            test_results["fan_speeds"] = f"FAILED: {str(e)}"
        
        # 5. WAN status
        _LOGGER.info("Fetching WAN status...")
        try:
            wan_status = await api.get_wan_status()
            _LOGGER.info("WAN status: %s", json.dumps(wan_status, indent=2))
            
            # Verify the WAN status structure
            verify_wan_status(wan_status)
            
            # Save to file
            with open(output_dir / "wan_status.json", "w") as f:
                json.dump(wan_status, f, indent=2)
                
            test_results["wan_status"] = "PASSED"
            
            # Store WAN interfaces for traffic stats verification
            wan_interfaces = []
            if "connection" in wan_status:
                for conn in wan_status["connection"]:
                    if "id" in conn:
                        wan_interfaces.append(conn["id"])
                        
            # Store in test_context for use by other tests
            test_context = {"wan_interfaces": wan_interfaces}
        except Exception as e:
            _LOGGER.error("Error during wan_status test: %s", e)
            test_results["wan_status"] = f"FAILED: {str(e)}"
            test_context = {"wan_interfaces": []}
        
        # 6. Client information
        _LOGGER.info("Fetching client information...")
        try:
            clients = await api.get_clients()
            _LOGGER.info("Client information: %s", json.dumps(clients, indent=2))
            
            # Verify the clients structure
            verify_clients(clients)
            
            # Save to file
            with open(output_dir / "clients.json", "w") as f:
                json.dump(clients, f, indent=2)
                
            test_results["clients"] = "PASSED"
        except Exception as e:
            _LOGGER.error("Error during clients test: %s", e)
            test_results["clients"] = f"FAILED: {str(e)}"
        
        # 7. Traffic statistics
        _LOGGER.info("Fetching traffic statistics...")
        try:
            traffic_stats = await api.get_traffic_stats()
            _LOGGER.info("Traffic statistics: %s", json.dumps(traffic_stats, indent=2))
            
            # Verify the traffic statistics structure using WAN interfaces from WAN status
            verify_traffic_stats(traffic_stats, test_context.get("wan_interfaces", []))
            
            # Save to file
            with open(output_dir / "traffic_stats.json", "w") as f:
                json.dump(traffic_stats, f, indent=2)
                
            test_results["traffic_stats"] = "PASSED"
        except Exception as e:
            _LOGGER.error("Error during traffic_stats test: %s", e)
            test_results["traffic_stats"] = f"FAILED: {str(e)}"
        
        # 8. Location information from GPS
        _LOGGER.info("Fetching location information...")
        try:
            location_info = await api.get_location()
            _LOGGER.info("Location information: %s", json.dumps(location_info, indent=2))
            
            # Verify the location information structure
            verify_location(location_info)
            
            # Save to file
            with open(output_dir / "location_info.json", "w") as f:
                json.dump(location_info, f, indent=2)
                
            test_results["location"] = "PASSED"
        except Exception as e:
            _LOGGER.error("Error during location test: %s", e)
            test_results["location"] = f"FAILED: {str(e)}"
        
        _LOGGER.info("All API tests completed")
        _LOGGER.info("Output files saved to %s", output_dir)
        
        # Print test summary
        _LOGGER.info("\n----- TEST SUMMARY -----")
        passed_tests = 0
        failed_tests = 0
        
        for test_name, result in test_results.items():
            if result == "PASSED":
                passed_tests += 1
                _LOGGER.info("✅ %s: %s", test_name, result)
            else:
                failed_tests += 1
                _LOGGER.error("❌ %s: %s", test_name, result)
                
        _LOGGER.info("-----------------------")
        _LOGGER.info("SUMMARY: %d tests passed, %d tests failed", passed_tests, failed_tests)
        _LOGGER.info("-----------------------")
        
        # Overall success if all tests passed
        return failed_tests == 0
    
    except Exception as e:
        _LOGGER.exception("Error during API testing: %s", e)
        return False
    
    finally:
        # Close the API session
        await api.close()


def verify_system_info(system_info):
    """Verify that the system_info response matches the expected structure."""
    # Check for required top-level keys
    assert "device_info" in system_info, "Missing 'device_info' in system_info"
    assert "thermal_sensors" in system_info, "Missing 'thermal_sensors' in system_info"
    assert "fan_speeds" in system_info, "Missing 'fan_speeds' in system_info"
    assert "system_time" in system_info, "Missing 'system_time' in system_info"
    
    # Verify device_info structure
    device_info = system_info["device_info"]
    assert "serial_number" in device_info, "Missing 'serial_number' in device_info"
    assert "name" in device_info, "Missing 'name' in device_info"
    assert "model" in device_info, "Missing 'model' in device_info"
    assert "firmware_version" in device_info, "Missing 'firmware_version' in device_info"
    
    # Verify thermal_sensors structure
    thermal_sensors = system_info["thermal_sensors"]
    assert "sensors" in thermal_sensors, "Missing 'sensors' in thermal_sensors"
    
    # Verify fan_speeds structure
    fan_speeds = system_info["fan_speeds"]
    assert "fans" in fan_speeds, "Missing 'fans' in fan_speeds"
    
    # Verify system_time structure
    system_time = system_info["system_time"]
    if system_time:  # Some routers might not provide system time
        assert "timestamp" in system_time, "Missing 'timestamp' in system_time"
    
    _LOGGER.info("System info structure verification passed")


def verify_device_info(device_info):
    """Verify that the device_info response matches the expected structure."""
    assert "device_info" in device_info, "Missing 'device_info' in device_info response"
    
    info = device_info["device_info"]
    assert "serial_number" in info, "Missing 'serial_number' in device_info"
    assert "name" in info, "Missing 'name' in device_info"
    assert "model" in info, "Missing 'model' in device_info"
    assert "firmware_version" in info, "Missing 'firmware_version' in device_info"
    
    _LOGGER.info("Device info structure verification passed")


def verify_thermal_sensors(thermal_sensors):
    """Verify that the thermal_sensors response matches the expected structure."""
    assert "sensors" in thermal_sensors, "Missing 'sensors' in thermal_sensors"
    
    sensors = thermal_sensors["sensors"]
    if sensors:  # Some routers might not have thermal sensors
        for sensor in sensors:
            assert "name" in sensor, "Missing 'name' in sensor"
            assert "temperature" in sensor, "Missing 'temperature' in sensor"
            assert "unit" in sensor, "Missing 'unit' in sensor"
    
    _LOGGER.info("Thermal sensors structure verification passed")


def verify_fan_speeds(fan_speeds):
    """Verify that the fan_speeds response matches the expected structure."""
    assert "fans" in fan_speeds, "Missing 'fans' in fan_speeds"
    
    fans = fan_speeds["fans"]
    if fans:  # Some routers might not have fans
        for fan in fans:
            assert "name" in fan, "Missing 'name' in fan"
            assert "speed" in fan, "Missing 'speed' in fan"
            assert "unit" in fan, "Missing 'unit' in fan"
    
    _LOGGER.info("Fan speeds structure verification passed")


def verify_wan_status(wan_status):
    """Verify that the wan_status response matches the expected structure."""
    assert "connection" in wan_status, "Missing 'connection' in wan_status"
    
    connections = wan_status["connection"]
    if connections:  # Router should have at least one WAN connection
        for conn in connections:
            assert "id" in conn, "Missing 'id' in WAN connection"
            assert "name" in conn, "Missing 'name' in WAN connection"
            assert "status" in conn, "Missing 'status' in WAN connection"
    
    _LOGGER.info("WAN status structure verification passed")


def verify_clients(clients):
    """Verify that the clients response matches the expected structure."""
    assert "client" in clients, "Missing 'client' in clients"
    
    client_list = clients["client"]
    if client_list:  # There might be no clients connected
        for client in client_list:
            assert "mac" in client, "Missing 'mac' in client"
            assert "name" in client, "Missing 'name' in client"
            assert "connected" in client, "Missing 'connected' in client"
    
    _LOGGER.info("Clients structure verification passed")


def verify_traffic_stats(traffic_stats, wan_interfaces=None):
    """
    Verify that the traffic_stats response matches the expected structure.
    
    Args:
        traffic_stats: Dictionary containing traffic statistics
        wan_interfaces: List of WAN interface IDs from the WAN status endpoint
    """
    assert "stats" in traffic_stats, "Missing 'stats' in traffic_stats"
    
    stats = traffic_stats["stats"]
    
    # Check that stats exist for WAN interfaces
    if wan_interfaces and len(wan_interfaces) > 0:
        if not stats:
            raise AssertionError(f"No traffic statistics returned despite having {len(wan_interfaces)} WAN interfaces: {wan_interfaces}")
        
        # Create a set of WAN IDs from the traffic stats
        traffic_wan_ids = {stat.get("wan_id") for stat in stats if "wan_id" in stat}
        
        # Check if we have at least one match between WAN interfaces and traffic stats
        if not traffic_wan_ids.intersection(wan_interfaces):
            raise AssertionError(f"None of the WAN interfaces {wan_interfaces} have traffic statistics")
            
        # Report on missing WAN interfaces but don't fail (some might be disconnected)
        missing_wans = []
        for wan_id in wan_interfaces:
            if wan_id not in traffic_wan_ids:
                missing_wans.append(wan_id)
                
        if missing_wans:
            _LOGGER.warning("Missing traffic stats for WAN interfaces: %s", missing_wans)
    
    # Verify the structure of each stat entry
    if stats:
        for stat in stats:
            assert "wan_id" in stat, "Missing 'wan_id' in traffic stat"
            assert "name" in stat, "Missing 'name' in traffic stat"
            assert "rx_bytes" in stat, "Missing 'rx_bytes' in traffic stat"
            assert "tx_bytes" in stat, "Missing 'tx_bytes' in traffic stat"
            assert "rx_rate" in stat, "Missing 'rx_rate' in traffic stat"
            assert "tx_rate" in stat, "Missing 'tx_rate' in traffic stat"
            assert "unit" in stat, "Missing 'unit' in traffic stat"
    
    _LOGGER.info("Traffic stats structure verification passed")


def verify_location(location_info):
    """Verify that the location_info response matches the expected structure."""
    assert "gps" in location_info, "Missing 'gps' in location_info"
    
    # If GPS is enabled, verify location data
    if location_info.get("gps", False) and "location" in location_info:
        location = location_info["location"]
        assert "latitude" in location, "Missing 'latitude' in location"
        assert "longitude" in location, "Missing 'longitude' in location"
        # Other fields might be optional depending on GPS quality
    
    _LOGGER.info("Location info structure verification passed")


def load_config():
    """Load configuration from .env file."""
    # Try to find .env file in the project root
    env_path = Path(__file__).parent.parent / '.env'
    
    if not env_path.exists():
        # Create a template .env file if it doesn't exist
        _LOGGER.info("Creating template .env file at %s", env_path)
        with open(env_path, 'w') as f:
            f.write("""# Peplink API test configuration
PEPLINK_ROUTER_IP=192.168.1.1
PEPLINK_USERNAME=admin
PEPLINK_PASSWORD=your_password
PEPLINK_VERIFY_SSL=false
""")
        _LOGGER.info("Please edit the .env file with your Peplink router details")
        sys.exit(1)
    
    # Load the .env file
    _LOGGER.info("Loading configuration from %s", env_path)
    load_dotenv(env_path)
    
    # Get configuration from environment variables
    router_ip = os.getenv("PEPLINK_ROUTER_IP")
    username = os.getenv("PEPLINK_USERNAME")
    password = os.getenv("PEPLINK_PASSWORD")
    verify_ssl = os.getenv("PEPLINK_VERIFY_SSL", "false").lower() == "true"
    
    if not router_ip or not username or not password:
        _LOGGER.error("Missing required configuration in .env file")
        sys.exit(1)
    
    return router_ip, username, password, verify_ssl


async def main():
    """Run the main test function."""
    _LOGGER.info("Starting Peplink API test")
    
    # Load configuration
    router_ip, username, password, verify_ssl = load_config()
    
    # Test the API
    success = await test_api(router_ip, username, password, verify_ssl)
    
    if success:
        _LOGGER.info("API test completed successfully")
    else:
        _LOGGER.error("API test failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
