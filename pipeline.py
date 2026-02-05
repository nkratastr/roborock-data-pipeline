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
    Tries saved token first, falls back to verification code.
    """
    collector = RoborockDataCollector(ROBOROCK_EMAIL)
    
    # Try saved authentication first
    if await collector.authenticate_with_saved_token():
        print("[AUTH] Using saved authentication token")
        try:
            await collector.discover_devices()
            return collector
        except Exception as e:
            print(f"[WARN] Saved token expired or invalid: {e}")
            # Fall through to request new code
    
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
    needs_setup_file = Path("config/.needs_setup")
    
    if spreadsheet_id_file.exists():
        spreadsheet_id = spreadsheet_id_file.read_text().strip()
        print(f"[SETUP] Using existing spreadsheet: {spreadsheet_id}")
        client = GoogleSheetsClient(str(creds_path), spreadsheet_id)
        
        # Set up sheets if needed (first time or flag exists)
        if needs_setup_file.exists() or not spreadsheet_id_file.with_suffix('.txt.setup_done').exists():
            print("[SETUP] Setting up spreadsheet sheets...")
            from src.roborock_collector import (
                CLEANING_HISTORY_HEADERS, 
                DEVICE_STATUS_HEADERS,
                CLEAN_SUMMARY_HEADERS,
                CONSUMABLES_HEADERS
            )
            
            # Create sheets
            for sheet_name in ["Cleaning_History", "Device_Status", "Clean_Summary", "Consumables", "Daily_Summary"]:
                try:
                    client.create_sheet(sheet_name)
                except:
                    pass  # Sheet might already exist
            
            # Write headers
            client.write_headers("Cleaning_History", CLEANING_HISTORY_HEADERS)
            client.write_headers("Device_Status", DEVICE_STATUS_HEADERS)
            client.write_headers("Clean_Summary", CLEAN_SUMMARY_HEADERS)
            client.write_headers("Consumables", CONSUMABLES_HEADERS)
            client.write_headers("Daily_Summary", ["Date", "Total_Cleanings", "Total_Area_m2", "Total_Time_min", "Avg_Area_m2", "Avg_Time_min"])
            
            # Mark as setup complete
            needs_setup_file.unlink(missing_ok=True)
            spreadsheet_id_file.with_suffix('.txt.setup_done').touch()
            print("[SETUP] Spreadsheet setup complete!")
            
        return client
    else:
        # Create new spreadsheet
        client = setup_roborock_spreadsheet(str(creds_path), SPREADSHEET_NAME)
        
        # Save spreadsheet ID for future runs
        spreadsheet_id_file.parent.mkdir(exist_ok=True)
        spreadsheet_id_file.write_text(client.spreadsheet_id)
        spreadsheet_id_file.with_suffix('.txt.setup_done').touch()
        
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
    
    print("\n" + "=" * 50)
    
    for device in collector.devices:
        # Get device status
        status = await collector.get_device_status(device)
        if status:
            print(f"\nDevice: {status.device_name}")
            print("-" * 40)
            print(f"  State: {status.state}")
            print(f"  Battery: {status.battery}%")
            print(f"  Clean Area: {status.clean_area} m²")
            print(f"  Clean Time: {status.clean_time} min")
            print(f"  Fan Power: {status.fan_power}")
            print(f"  Water Box Status: {status.water_box_status}")
            print(f"  Water Box Mode: {status.water_box_mode}")
            print(f"  Mop Mode: {status.mop_mode}")
            if status.error_code:
                print(f"  Error Code: {status.error_code}")
        
        # Get clean summary
        clean_summary = await collector.get_clean_summary(device)
        if clean_summary:
            print("\n  [Clean Summary - Lifetime Stats]")
            print(f"    Total Cleanings: {clean_summary.total_clean_count}")
            print(f"    Total Area: {clean_summary.total_clean_area} m²")
            print(f"    Total Time: {clean_summary.total_clean_time} min")
        
        # Get consumables
        consumables = await collector.get_consumables(device)
        if consumables:
            print("\n  [Consumables - Work Time (hours)]")
            print(f"    Main Brush: {consumables.main_brush_life}")
            print(f"    Side Brush: {consumables.side_brush_life}")
            print(f"    Filter: {consumables.filter_life}")
            print(f"    Sensor: {consumables.sensor_dirty_time}")
            print(f"    Mop Pad: {consumables.mop_pad_life}")
    
    print("\n" + "=" * 50)


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


async def smart_sync():
    """
    Smart sync - only logs if new cleaning detected since last run.
    Uses total_clean_count to detect new cleanings.
    """
    from src.state_manager import StateManager
    
    print("\n[SMART SYNC] Checking for new cleanings...")
    
    state_manager = StateManager()
    
    collector = await setup_and_authenticate()
    if not collector:
        return
    
    sheets_client = setup_sheets()
    if not sheets_client:
        print("[ERROR] Google Sheets not configured")
        return
    
    for device in collector.devices:
        # Get clean summary with total count
        clean_summary = await collector.get_clean_summary(device)
        if not clean_summary:
            print(f"[WARN] Could not get clean summary for {device.name}")
            continue
        
        current_count = clean_summary.total_clean_count
        device_name = device.name
        
        # Check if new cleaning occurred
        if state_manager.has_new_cleaning(device_name, current_count):
            new_cleanings = state_manager.get_new_cleaning_count(device_name, current_count)
            print(f"[NEW] {new_cleanings} new cleaning(s) detected for {device_name}!")
            
            # Log current device state
            status = await collector.get_device_status(device)
            if status:
                sheets_client.append_row("Device_Status", status.to_row())
            
            # Log clean summary
            from datetime import datetime
            summary_row = [
                datetime.now().isoformat(),
                device_name,
                clean_summary.total_clean_count,
                clean_summary.total_clean_area,
                clean_summary.total_clean_time
            ]
            sheets_client.append_row("Clean_Summary", summary_row)
            
            # Log consumables
            consumables = await collector.get_consumables(device)
            if consumables:
                consumables_row = [
                    datetime.now().isoformat(),
                    device_name,
                    consumables.main_brush_life,
                    consumables.side_brush_life,
                    consumables.filter_life,
                    consumables.sensor_dirty_time,
                    consumables.mop_pad_life
                ]
                sheets_client.append_row("Consumables", consumables_row)
            
            # Update state
            state_manager.update_device_state(
                device_name,
                current_count,
                clean_summary.total_clean_area,
                clean_summary.total_clean_time
            )
            
            print(f"[SUCCESS] Logged data for {device_name}")
        else:
            print(f"[SKIP] No new cleanings for {device_name} (count: {current_count})")
    
    print("[SMART SYNC] Done!")


async def schedule_sync(interval_seconds: int = 43200):
    """
    Run smart_sync on a schedule. Default: every 12 hours (43200 seconds).
    Perfect for Docker deployment.
    """
    print(f"\n[SCHEDULE] Starting scheduled sync every {interval_seconds // 3600} hours")
    print("[SCHEDULE] Press Ctrl+C to stop\n")
    
    while True:
        try:
            await smart_sync()
            print(f"\n[SCHEDULE] Next sync in {interval_seconds // 3600} hours...")
            await asyncio.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\n[SCHEDULE] Stopping...")
            break
        except Exception as e:
            print(f"[ERROR] Schedule sync error: {e}")
            # Wait before retrying
            await asyncio.sleep(60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Roborock Q8 Data Pipeline")
    parser.add_argument(
        "--mode",
        choices=["monitor", "status", "log", "smart", "schedule"],
        default="smart",
        help="Mode: monitor (continuous), status (one-time), log (manual), smart (detect new), schedule (periodic smart)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=43200,
        help="Interval in seconds for schedule mode (default: 43200 = 12 hours)"
    )
    
    args = parser.parse_args()
    
    if args.mode == "monitor":
        asyncio.run(main())
    elif args.mode == "status":
        asyncio.run(quick_status())
    elif args.mode == "log":
        asyncio.run(log_single_cleaning())
    elif args.mode == "smart":
        asyncio.run(smart_sync())
    elif args.mode == "schedule":
        asyncio.run(schedule_sync(args.interval))
