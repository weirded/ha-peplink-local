#!/usr/bin/env python3
"""
Standalone test script for the Peplink API client.

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

# Add the parent directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import only the API client directly
from custom_components.peplink_local.peplink_api import PeplinkAPI

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
logger = logging.getLogger(__name__)

# Create an insecure SSL context (copied from the API client to avoid imports)
def create_insecure_ssl_context():
    """Create an insecure SSL context that doesn't verify SSL certificates."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context

async def test_api(router_ip, username, password, verify_ssl=False):
    """Test the Peplink API by connecting and fetching data."""
    logger.info("Creating PeplinkAPI instance for %s", router_ip)
    api = PeplinkAPI(router_ip, username, password, verify_ssl=verify_ssl)
    
    # Create output directory if it doesn't exist
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    
    try:
        # Test connection
        logger.info("Testing connection...")
        connected = await api.connect()
        if not connected:
            logger.error("Failed to connect to the Peplink router")
            return False
        
        logger.info("Successfully connected to the Peplink router")
        
        # 1. WAN status
        logger.info("Fetching WAN status...")
        wan_status = await api.get_wan_status()
        logger.info("WAN status: %s", json.dumps(wan_status, indent=2))
        
        # Save to file
        with open(output_dir / "wan_status.json", "w") as f:
            json.dump(wan_status, f, indent=2)
        
        # 2. Client information
        logger.info("Fetching client information...")
        clients = await api.get_clients()
        logger.info("Client information: %s", json.dumps(clients, indent=2))
        
        # Save to file
        with open(output_dir / "clients.json", "w") as f:
            json.dump(clients, f, indent=2)
        
        # 3. Thermal sensors
        logger.info("Fetching thermal sensor data...")
        thermal_sensors = await api.get_thermal_sensors()
        logger.info("Thermal sensor data: %s", json.dumps(thermal_sensors, indent=2))
        
        # Save to file
        with open(output_dir / "thermal_sensors.json", "w") as f:
            json.dump(thermal_sensors, f, indent=2)
        
        # 4. Fan speeds
        logger.info("Fetching fan speed data...")
        fan_speeds = await api.get_fan_speeds()
        logger.info("Fan speed data: %s", json.dumps(fan_speeds, indent=2))
        
        # Save to file
        with open(output_dir / "fan_speeds.json", "w") as f:
            json.dump(fan_speeds, f, indent=2)
        
        # 5. Traffic statistics
        logger.info("Fetching traffic statistics...")
        traffic_stats = await api.get_traffic_stats()
        logger.info("Traffic statistics: %s", json.dumps(traffic_stats, indent=2))
        
        # Save to file
        with open(output_dir / "traffic_stats.json", "w") as f:
            json.dump(traffic_stats, f, indent=2)
        
        logger.info("All API tests completed successfully")
        logger.info("Output files saved to %s", output_dir)
        
        return True
    
    except Exception as e:
        logger.exception("Error during API testing: %s", e)
        return False
    
    finally:
        # Close the API session
        await api.close()


def load_config():
    """Load configuration from .env file."""
    # Try to find .env file in the project root
    env_path = Path(__file__).parent.parent / '.env'
    
    if not env_path.exists():
        # Create a template .env file if it doesn't exist
        logger.info("Creating template .env file at %s", env_path)
        with open(env_path, 'w') as f:
            f.write("""# Peplink API test configuration
PEPLINK_ROUTER_IP=192.168.1.1
PEPLINK_USERNAME=admin
PEPLINK_PASSWORD=your_password
PEPLINK_VERIFY_SSL=false
""")
        logger.info("Please edit the .env file with your Peplink router details")
        sys.exit(1)
    
    # Load the .env file
    logger.info("Loading configuration from %s", env_path)
    load_dotenv(env_path)
    
    # Get configuration from environment variables
    router_ip = os.getenv("PEPLINK_ROUTER_IP")
    username = os.getenv("PEPLINK_USERNAME")
    password = os.getenv("PEPLINK_PASSWORD")
    verify_ssl = os.getenv("PEPLINK_VERIFY_SSL", "false").lower() == "true"
    
    if not router_ip or not username or not password:
        logger.error("Missing required configuration in .env file")
        sys.exit(1)
    
    return router_ip, username, password, verify_ssl


async def main():
    """Run the main test function."""
    logger.info("Starting Peplink API test")
    
    # Load configuration
    router_ip, username, password, verify_ssl = load_config()
    
    # Test the API
    success = await test_api(router_ip, username, password, verify_ssl)
    
    if success:
        logger.info("API test completed successfully")
    else:
        logger.error("API test failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
