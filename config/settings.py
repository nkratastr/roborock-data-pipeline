"""
Configuration settings for Roborock Data Pipeline
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Roborock Account Settings
ROBOROCK_EMAIL = os.getenv("ROBOROCK_EMAIL")

if not ROBOROCK_EMAIL:
    raise ValueError("ROBOROCK_EMAIL environment variable is not set. "
                     "Create a .env file with ROBOROCK_EMAIL=your-email@example.com")

# Google Sheets Settings
GOOGLE_SHEETS_CREDENTIALS_FILE = "config/credentials.json"
SPREADSHEET_NAME = "Roborock_Q8_Data"

# Sheet names for different data types
SHEETS = {
    "cleaning_history": "Cleaning_History",
    "daily_summary": "Daily_Summary",
    "consumables": "Consumables",
    "device_status": "Device_Status"
}

# Data collection settings
POLLING_INTERVAL_SECONDS = 60  # Check device status every 60 seconds
CLEANING_END_WAIT_SECONDS = 120  # Wait time after cleaning ends to capture final data

# Cleaning states
CLEANING_STATES = ["cleaning", "segment_cleaning", "zone_cleaning", "spot_cleaning"]
IDLE_STATES = ["charger", "idle", "paused", "charging"]
