#!/bin/bash
# Run the Peplink API test script

# Check if the tests directory exists
if [ ! -d "$(dirname "$0")" ]; then
    echo "Error: tests directory not found"
    exit 1
fi

# Make sure we're in the project root directory
cd "$(dirname "$0")/.."

# Make the test script executable
chmod +x "./tests/standalone_test.py"

# Install required dependencies
echo "Installing required dependencies from requirements.txt"
pip install -r requirements.txt

# Check if .env file exists, if not, copy from example
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    echo "Creating .env file from .env.example"
    cp ".env.example" ".env"
    echo "Please edit the .env file with your Peplink router details"
    exit 1
fi

# Run the test script
echo "Running API test script"
python3 "./tests/standalone_test.py"
