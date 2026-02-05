"""
Roborock Q8 Data Pipeline
Main script for collecting cleaning data and storing in Google Sheets

This script monitors your Roborock Q8 and automatically logs cleaning
sessions to Google Sheets when they complete.
"""

import asyncio
import sys
import os
from datetime import datetime
from pathlib import Path

# Fix Windows asyncio compatibility issue with Python 3.8+
# ProactorEventLoop doesn't support add_reader/add_writer needed by MQTT
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import (
    ROBOROCK_EMAIL,
    GOOGLE_SHEETS_CREDENTIALS_FILE,
    SPREADSHEET_NAME,
    POLLING_INTERVAL_SECONDS
)
from src.roborock_collector import (
    RoborockDataCollector,
    CleaningRecord,
    DeviceStatus,
    CLEANING_HISTORY_HEADERS,
    DEVICE_STATUS_HEADERS
)
from src.sheets_client import GoogleSheetsClient, setup_roborock_spreadsheet


class CleaningMonitor:
    """
    Monitors Roborock device and logs cleaning sessions.
    """
    
    def __init__(
        self,
        collector: RoborockDataCollector,
        sheets_client: GoogleSheetsClient
    ):
        self.collector = collector
        self.sheets_client = sheets_client
        self.previous_states = {}  # Track previous state per device
        self.cleaning_start_battery = {}  # Track battery at cleaning start
        self._running = False
    
    async def monitor_loop(self):
        """
        Main monitoring loop - polls device status and logs completed cleanings.
        """
        print("\n[MONITOR] Starting cleaning monitor...")
        print(f"[MONITOR] Polling interval: {POLLING_INTERVAL_SECONDS} seconds")
        print("[MONITOR] Press Ctrl+C to stop\n")
        
        self._running = True
        
        while self._running:
            try:
                for device in self.collector.devices:
                    await self._check_device(device)
                
                await asyncio.sleep(POLLING_INTERVAL_SECONDS)
                
            except KeyboardInterrupt:
                print("\n[MONITOR] Stopping monitor...")
                self._running = False
            except Exception as e:
                print(f"[ERROR] Monitor error: {e}")
                await asyncio.sleep(POLLING_INTERVAL_SECONDS)
    
    async def _check_device(self, device):
        """
        Check a device's status and log if cleaning just completed.
        """
        status = await self.collector.get_device_status(device)
        if not status:
            return
        
        device_id = status.device_name
        previous_state = self.previous_states.get(device_id)
        
        # Detect cleaning start
        if self.collector.is_cleaning(status):
            if device_id not in self.cleaning_start_battery:
                self.cleaning_start_battery[device_id] = status.battery
                print(f"[MONITOR] {device_id}: Cleaning started (Battery: {status.battery}%)")
        
        # Detect cleaning end
        if previous_state:
            was_cleaning = self.collector.is_cleaning(previous_state)
            is_now_idle = self.collector.is_idle(status)
            
            if was_cleaning and is_now_idle:
                print(f"[MONITOR] {device_id}: Cleaning completed!")
                await self._log_cleaning_session(device, status)
        
        # Update previous state
        self.previous_states[device_id] = status
        
        # Print periodic status
        print(f"[STATUS] {device_id}: {status.state} | Battery: {status.battery}% | "
              f"Area: {status.clean_area}m² | Time: {status.clean_time}min")
    
    async def _log_cleaning_session(self, device, final_status: DeviceStatus):
        """
        Log a completed cleaning session to Google Sheets.
        """
        device_id = final_status.device_name
        battery_start = self.cleaning_start_battery.pop(device_id, None)
        
        record = CleaningRecord(
            timestamp=datetime.now().isoformat(),
            device_name=device_id,
            clean_time_minutes=final_status.clean_time,
            clean_area_sqm=final_status.clean_area,
            battery_start=battery_start,
            battery_end=final_status.battery,
            fan_power=final_status.fan_power,
            water_level=str(final_status.water_box_status) if final_status.water_box_status else None,
            mop_mode=final_status.mop_mode,
            state="completed",
            error_code=final_status.error_code
        )
        
        try:
            self.sheets_client.append_row("Cleaning_History", record.to_row())
            print(f"[SUCCESS] Logged cleaning: {record.clean_area_sqm}m² in {record.clean_time_minutes}min")
        except Exception as e:
            print(f"[ERROR] Failed to log to sheets: {e}")


async def setup_and_authenticate():
    """
    Set up collector and authenticate with Roborock.
    """
    collector = RoborockDataCollector(ROBOROCK_EMAIL)
    
    # Request verification code
    print(f"\n[SETUP] Sending verification code to {ROBOROCK_EMAIL}...")
    await collector.request_verification_code()
    
    # Get code from user
    code = input("\nEnter the verification code from your email: ")
    
    # Authenticate
    if not await collector.authenticate(code):
        print("[ERROR] Authentication failed!")
        return None
    
    # Discover devices
    await collector.discover_devices()
    
    return collector


def setup_sheets():
    """
    Set up Google Sheets client.
    """
    creds_path = Path(GOOGLE_SHEETS_CREDENTIALS_FILE)
    
    if not creds_path.exists():
        print(f"\n[SETUP] Google Sheets credentials not found at: {creds_path}")
        print("[SETUP] Please follow these steps:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. Create a new project (or select existing)")
        print("  3. Enable 'Google Sheets API'")
        print("  4. Create Service Account credentials")
        print("  5. Download JSON key file")
        print(f"  6. Save it as: {creds_path.absolute()}")
        return None
    
    # Check if we have an existing spreadsheet ID
    spreadsheet_id_file = Path("config/spreadsheet_id.txt")
    
    if spreadsheet_id_file.exists():
        spreadsheet_id = spreadsheet_id_file.read_text().strip()
        print(f"[SETUP] Using existing spreadsheet: {spreadsheet_id}")
        return GoogleSheetsClient(str(creds_path), spreadsheet_id)
    else:
        # Create new spreadsheet
        client = setup_roborock_spreadsheet(str(creds_path), SPREADSHEET_NAME)
        
        # Save spreadsheet ID for future runs
        spreadsheet_id_file.parent.mkdir(exist_ok=True)
        spreadsheet_id_file.write_text(client.spreadsheet_id)
        
        return client


async def main():
    """
    Main entry point for the data pipeline.
    """
    print("\n" + "=" * 60)
    print("       ROBOROCK Q8 DATA PIPELINE")
    print("=" * 60)
    
    # Setup Google Sheets
    print("\n[1/3] Setting up Google Sheets...")
    sheets_client = setup_sheets()
    if not sheets_client:
        print("\n[INFO] Running in demo mode without Google Sheets")
        sheets_client = None
    
    # Authenticate with Roborock
    print("\n[2/3] Authenticating with Roborock...")
    collector = await setup_and_authenticate()
    if not collector:
        return
    
    # Start monitoring
    print("\n[3/3] Starting monitor...")
    
    if sheets_client:
        monitor = CleaningMonitor(collector, sheets_client)
        await monitor.monitor_loop()
    else:
        # Demo mode - just show status
        print("\n[DEMO] Showing device status (no logging)")
        while True:
            try:
                statuses = await collector.get_all_device_statuses()
                for status in statuses:
                    print(f"\n[STATUS] {status.device_name}:")
                    print(f"  State: {status.state}")
                    print(f"  Battery: {status.battery}%")
                    print(f"  Clean Area: {status.clean_area}m²")
                    print(f"  Clean Time: {status.clean_time}min")
                
                await asyncio.sleep(POLLING_INTERVAL_SECONDS)
            except KeyboardInterrupt:
                print("\n[EXIT] Goodbye!")
                break


async def quick_status():
    """
    Quick check - just get and display current device status.
    """
    print("\n[QUICK STATUS] Getting device status...")
    
    collector = await setup_and_authenticate()
    if not collector:
        return
    
    statuses = await collector.get_all_device_statuses()
    
    print("\n" + "=" * 40)
    for status in statuses:
        print(f"\nDevice: {status.device_name}")
        print(f"  State: {status.state}")
        print(f"  Battery: {status.battery}%")
        print(f"  Clean Area: {status.clean_area} m²")
        print(f"  Clean Time: {status.clean_time} min")
        print(f"  Fan Power: {status.fan_power}")
        print(f"  Mop Mode: {status.mop_mode}")
    print("=" * 40)


async def log_single_cleaning():
    """
    Manually log a single cleaning session (useful for testing).
    """
    print("\n[MANUAL LOG] Logging current cleaning data...")
    
    collector = await setup_and_authenticate()
    if not collector:
        return
    
    sheets_client = setup_sheets()
    if not sheets_client:
        print("[ERROR] Google Sheets not configured")
        return
    
    for device in collector.devices:
        record = await collector.create_cleaning_record(device)
        if record:
            sheets_client.append_row("Cleaning_History", record.to_row())
            print(f"[SUCCESS] Logged: {record.clean_area_sqm}m² in {record.clean_time_minutes}min")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Roborock Q8 Data Pipeline")
    parser.add_argument(
        "--mode",
        choices=["monitor", "status", "log"],
        default="monitor",
        help="Mode: monitor (continuous), status (one-time), log (manual log)"
    )
    
    args = parser.parse_args()
    
    if args.mode == "monitor":
        asyncio.run(main())
    elif args.mode == "status":
        asyncio.run(quick_status())
    elif args.mode == "log":
        asyncio.run(log_single_cleaning())
