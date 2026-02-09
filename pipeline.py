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
    POLLING_INTERVAL_SECONDS,
    GOOGLE_SHEETS_ENABLED,
    GOOGLE_SHEETS_SPREADSHEET_ID
)
from src.roborock_collector import (
    RoborockDataCollector,
    CleaningRecord,
    DeviceStatus,
    CleaningHistoryRecord,
    CLEANING_HISTORY_HEADERS,
    DEVICE_STATUS_HEADERS,
    CLEANING_RECORDS_HEADERS
)
from src.sheets_client import GoogleSheetsClient, setup_roborock_spreadsheet


def display_last_cleaning(record):
    """
    Display a cleaning record on screen in a formatted box.
    Works with CleaningRecord, CleaningHistoryRecord, or a raw row list.
    """
    print()
    print("+" + "=" * 46 + "+")
    print("|{:^46s}|".format("LAST CLEANING RECORD"))
    print("+" + "-" * 46 + "+")

    if hasattr(record, 'device_name'):
        # CleaningRecord
        print("|  Device:    {:<33s}|".format(str(record.device_name or "Unknown")))
        print("|  Date:      {:<33s}|".format(str(getattr(record, 'timestamp', '')[:19])))
        print("|  Duration:  {:<33s}|".format(f"{record.clean_time_minutes} min"))
        print("|  Area:      {:<33s}|".format(f"{record.clean_area_sqm} m2"))
        if hasattr(record, 'fan_power') and record.fan_power:
            print("|  Fan Power: {:<33s}|".format(str(record.fan_power)))
        if hasattr(record, 'mop_mode') and record.mop_mode:
            print("|  Mop Mode:  {:<33s}|".format(str(record.mop_mode)))
        if hasattr(record, 'state') and record.state:
            print("|  Status:    {:<33s}|".format(str(record.state)))
        if hasattr(record, 'error_code') and record.error_code:
            print("|  Error:     {:<33s}|".format(str(record.error_code)))
    elif hasattr(record, 'start_time'):
        # CleaningHistoryRecord
        print("|  Device:    {:<33s}|".format(str(getattr(record, 'device_name', 'Unknown'))))
        print("|  Date:      {:<33s}|".format(str(record.start_time[:19])))
        print("|  Duration:  {:<33s}|".format(f"{record.duration_minutes} min"))
        print("|  Area:      {:<33s}|".format(f"{record.area_sqm} m2"))
        if record.clean_mode:
            print("|  Mode:      {:<33s}|".format(str(record.clean_mode)))
        if record.clean_way:
            print("|  Method:    {:<33s}|".format(str(record.clean_way)))
        if record.task_status:
            print("|  Status:    {:<33s}|".format(str(record.task_status)))
        if record.error_code:
            print("|  Error:     {:<33s}|".format(str(record.error_code)))
    elif isinstance(record, (list, tuple)):
        # Raw row data
        labels = ["Timestamp", "Device", "Value 1", "Value 2", "Value 3"]
        for i, val in enumerate(record):
            label = labels[i] if i < len(labels) else f"Field {i+1}"
            print("|  {:<10s}: {:<32s}|".format(label, str(val)[:32]))

    print("+" + "=" * 46 + "+")
    print()


class CleaningMonitor:
    """
    Monitors Roborock device and logs cleaning sessions.
    """
    
    def __init__(
        self,
        collector: RoborockDataCollector,
        sheets_client: GoogleSheetsClient = None
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
        
        if self.sheets_client:
            try:
                self.sheets_client.append_row("Cleaning_History", record.to_row())
                print(f"[SUCCESS] Logged cleaning to Google Sheets: {record.clean_area_sqm}m² in {record.clean_time_minutes}min")
            except Exception as e:
                print(f"[WARN] Google Sheets write failed: {e}")
                print("[INFO] Displaying cleaning record on screen instead:")
                display_last_cleaning(record)
        else:
            print("[INFO] Google Sheets not available — displaying on screen:")
            display_last_cleaning(record)


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
    If credentials are missing, prompts the user interactively.
    If Google Sheets is disabled via env, returns None.
    """
    # Check if Google Sheets is disabled via environment variable
    if not GOOGLE_SHEETS_ENABLED:
        print("[SETUP] Google Sheets is disabled (GOOGLE_SHEETS_ENABLED=false)")
        print("[INFO] Cleaning data will be displayed on screen only")
        return None

    creds_path = Path(GOOGLE_SHEETS_CREDENTIALS_FILE)

    if not creds_path.exists():
        print(f"\n[SETUP] Google Sheets credentials not found at: {creds_path}")
        print("\nWhat would you like to do?")
        print("  1. Enter the path to your credentials.json file")
        print("  2. Continue without Google Sheets (display mode only)")
        print()

        choice = input("Enter your choice (1-2): ").strip()

        if choice == "1":
            custom_path = input("Enter the full path to your credentials.json: ").strip()
            custom_path = Path(custom_path)
            if custom_path.exists():
                # Copy credentials to expected location
                import shutil
                creds_path.parent.mkdir(exist_ok=True)
                shutil.copy2(str(custom_path), str(creds_path))
                print(f"[SUCCESS] Credentials copied to {creds_path}")
            else:
                print(f"[ERROR] File not found: {custom_path}")
                print("[INFO] Continuing without Google Sheets")
                return None
        else:
            print("[INFO] Continuing without Google Sheets — data will display on screen")
            return None

    # Try to initialize the Google Sheets client
    spreadsheet_id_file = Path("config/spreadsheet_id.txt")
    needs_setup_file = Path("config/.needs_setup")

    try:
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
                    CONSUMABLES_HEADERS,
                    CLEANING_RECORDS_HEADERS
                )

                # Create sheets
                for sheet_name in ["Cleaning_History", "Device_Status", "Clean_Summary", "Consumables", "Daily_Summary", "Cleaning_Records"]:
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
                client.write_headers("Cleaning_Records", CLEANING_RECORDS_HEADERS)

                # Mark as setup complete
                needs_setup_file.unlink(missing_ok=True)
                spreadsheet_id_file.with_suffix('.txt.setup_done').touch()
                print("[SETUP] Spreadsheet setup complete!")

            return client

        elif GOOGLE_SHEETS_SPREADSHEET_ID:
            # Use spreadsheet ID from environment variable
            print(f"[SETUP] Using spreadsheet ID from environment: {GOOGLE_SHEETS_SPREADSHEET_ID}")
            spreadsheet_id_file.parent.mkdir(exist_ok=True)
            spreadsheet_id_file.write_text(GOOGLE_SHEETS_SPREADSHEET_ID)
            client = GoogleSheetsClient(str(creds_path), GOOGLE_SHEETS_SPREADSHEET_ID)
            return client

        else:
            # No spreadsheet ID — ask user
            print("\n[SETUP] No spreadsheet ID found.")
            print("  1. Enter your Google Sheets spreadsheet ID")
            print("  2. Create a new spreadsheet automatically")
            print("  3. Continue without Google Sheets (display mode only)")
            print()

            choice = input("Enter your choice (1-3): ").strip()

            if choice == "1":
                sid = input("Enter your spreadsheet ID: ").strip()
                if sid:
                    spreadsheet_id_file.parent.mkdir(exist_ok=True)
                    spreadsheet_id_file.write_text(sid)
                    client = GoogleSheetsClient(str(creds_path), sid)
                    print(f"[SUCCESS] Spreadsheet ID saved: {sid}")
                    return client
                else:
                    print("[WARN] No ID entered. Continuing without Google Sheets")
                    return None
            elif choice == "2":
                client = setup_roborock_spreadsheet(str(creds_path), SPREADSHEET_NAME)
                spreadsheet_id_file.parent.mkdir(exist_ok=True)
                spreadsheet_id_file.write_text(client.spreadsheet_id)
                spreadsheet_id_file.with_suffix('.txt.setup_done').touch()
                return client
            else:
                print("[INFO] Continuing without Google Sheets — data will display on screen")
                return None

    except Exception as e:
        print(f"\n[ERROR] Google Sheets setup failed: {e}")
        print("[INFO] Continuing without Google Sheets — data will display on screen")
        return None


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

    if not sheets_client:
        print("[INFO] Running without Google Sheets — completed cleanings will display on screen")

    monitor = CleaningMonitor(collector, sheets_client)
    await monitor.monitor_loop()


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
    Falls back to screen display if Google Sheets is unavailable.
    """
    print("\n[MANUAL LOG] Logging current cleaning data...")

    collector = await setup_and_authenticate()
    if not collector:
        return

    sheets_client = setup_sheets()
    if not sheets_client:
        print("[WARN] Google Sheets not configured — data will display on screen")

    for device in collector.devices:
        record = await collector.create_cleaning_record(device)
        if record:
            if sheets_client:
                try:
                    sheets_client.append_row("Cleaning_History", record.to_row())
                    print(f"[SUCCESS] Logged to Google Sheets: {record.clean_area_sqm}m² in {record.clean_time_minutes}min")
                except Exception as e:
                    print(f"[WARN] Google Sheets write failed: {e}")
                    display_last_cleaning(record)
            else:
                display_last_cleaning(record)


async def smart_sync():
    """
    Smart sync - only logs if new cleaning detected since last run.
    Uses total_clean_count to detect new cleanings.
    Falls back to screen display if Google Sheets is unavailable.
    """
    from src.state_manager import StateManager

    print("\n[SMART SYNC] Checking for new cleanings...")

    state_manager = StateManager()

    collector = await setup_and_authenticate()
    if not collector:
        return

    sheets_client = setup_sheets()
    if not sheets_client:
        print("[WARN] Google Sheets not configured — new cleanings will display on screen")

    sheets_failed = False

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

            # Get the latest cleaning record for display fallback
            latest_record = None
            records = await collector.get_clean_records(device, limit=1)
            if records:
                latest_record = records[0]

            if sheets_client and not sheets_failed:
                try:
                    # Log current device state
                    status = await collector.get_device_status(device)
                    if status:
                        sheets_client.append_row("Device_Status", status.to_row())

                    # Log clean summary
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

                    print(f"[SUCCESS] Logged data to Google Sheets for {device_name}")
                except Exception as e:
                    print(f"[WARN] Google Sheets write failed: {e}")
                    sheets_failed = True
                    if latest_record:
                        print("[INFO] Displaying last cleaning record on screen instead:")
                        display_last_cleaning(latest_record)
            else:
                # No sheets client or sheets already failed — display on screen
                if latest_record:
                    display_last_cleaning(latest_record)
                else:
                    print(f"[INFO] {device_name}: {new_cleanings} new cleaning(s), "
                          f"total area: {clean_summary.total_clean_area}m2, "
                          f"total time: {clean_summary.total_clean_time}min")

            # Update state regardless of sheets success
            state_manager.update_device_state(
                device_name,
                current_count,
                clean_summary.total_clean_area,
                clean_summary.total_clean_time
            )
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


async def fetch_cleaning_history(limit: int = 10):
    """
    Fetch historical cleaning records from device and log to Google Sheets.
    Falls back to screen display if Google Sheets is unavailable.

    Args:
        limit: Maximum number of records to fetch (default 10)
    """
    print(f"\n[HISTORY] Fetching last {limit} cleaning records...")

    collector = await setup_and_authenticate()
    if not collector:
        return

    sheets_client = setup_sheets()
    if not sheets_client:
        print("[WARN] Google Sheets not configured — records will display on screen only")

    # Ensure the Cleaning_Records sheet exists with headers
    if sheets_client:
        try:
            from src.roborock_collector import CLEANING_RECORDS_HEADERS
            sheets_client.create_sheet("Cleaning_Records")
            sheets_client.write_headers("Cleaning_Records", CLEANING_RECORDS_HEADERS)
        except:
            pass  # Sheet might already exist

    for device in collector.devices:
        device_name = getattr(device, 'name', 'Roborock Q8')
        print(f"\n[INFO] Fetching records for {device_name}...")

        records = await collector.get_clean_records(device, limit=limit)

        if not records:
            print(f"[WARN] No cleaning records found for {device_name}")
            continue

        print(f"[INFO] Found {len(records)} cleaning records")

        # Try to log each record to Google Sheets
        sheets_write_ok = False
        if sheets_client:
            try:
                for record in records:
                    sheets_client.append_row("Cleaning_Records", record.to_row())
                sheets_write_ok = True
                print(f"[SUCCESS] Logged {len(records)} cleaning records to Google Sheets for {device_name}")
            except Exception as e:
                print(f"[WARN] Google Sheets write failed: {e}")

        # Always display the records on screen (and especially if Sheets failed)
        if not sheets_write_ok:
            print("[INFO] Displaying cleaning records on screen:")

        print(f"\n{'=' * 60}")
        print(f"CLEANING HISTORY - {device_name}")
        print(f"{'=' * 60}")

        for i, record in enumerate(records, 1):
            print(f"\n[{i}] {record.start_time}")
            print(f"    Duration: {record.duration_minutes} min")
            print(f"    Area: {record.area_sqm} m2")
            if record.clean_mode:
                print(f"    Mode: {record.clean_mode}")
            if record.clean_way:
                print(f"    Method: {record.clean_way}")
            if record.error_code:
                print(f"    Error: {record.error_code}")
            if record.task_status:
                print(f"    Status: {record.task_status}")

        print(f"\n{'=' * 60}")

    print("\n[HISTORY] Done!")


async def sync_new_records():
    """
    Check for new cleaning records and log only new ones to Google Sheets.
    Uses state manager to track what's been logged.
    Falls back to screen display if Google Sheets is unavailable.
    """
    from src.state_manager import StateManager
    from src.roborock_collector import CLEANING_RECORDS_HEADERS

    print("\n[SYNC] Checking for new cleaning records...")

    collector = await setup_and_authenticate()
    if not collector:
        return False

    sheets_client = setup_sheets()
    if not sheets_client:
        print("[WARN] Google Sheets not configured — new records will display on screen")

    state_manager = StateManager()

    # Ensure the Cleaning_Records sheet exists
    if sheets_client:
        try:
            sheets_client.create_sheet("Cleaning_Records")
            sheets_client.write_headers("Cleaning_Records", CLEANING_RECORDS_HEADERS)
        except:
            pass

    new_records_found = False

    for device in collector.devices:
        device_name = getattr(device, 'name', 'Roborock Q8')

        # Get the last logged record timestamp
        last_timestamp = state_manager.get_last_record_timestamp(device_name)

        # Fetch recent records (limit to 5 to avoid re-logging too many)
        records = await collector.get_clean_records(device, limit=5)

        if not records:
            print(f"[INFO] No records found for {device_name}")
            continue

        # Filter to only new records
        new_records = []
        for record in records:
            # If no previous timestamp, only log the latest one
            if last_timestamp is None:
                new_records = [records[0]]  # Just the most recent
                break
            # Check if this record is newer than the last logged
            if record.start_time > last_timestamp:
                new_records.append(record)

        if not new_records:
            print(f"[INFO] No new records for {device_name} (last: {last_timestamp})")
            continue

        new_records_found = True
        print(f"[INFO] Found {len(new_records)} new record(s) for {device_name}")

        # Log new records (oldest first to maintain order)
        sheets_write_ok = True
        for record in reversed(new_records):
            if sheets_client and sheets_write_ok:
                try:
                    sheets_client.append_row("Cleaning_Records", record.to_row())
                    print(f"  [NEW] {record.start_time}: {record.duration_minutes}min, {record.area_sqm}m2")
                except Exception as e:
                    print(f"  [WARN] Google Sheets write failed: {e}")
                    sheets_write_ok = False
                    display_last_cleaning(record)
            else:
                display_last_cleaning(record)

        # Update the last timestamp to the most recent record
        state_manager.update_last_record_timestamp(device_name, records[0].start_time)

    return new_records_found


async def schedule_record_sync(interval_seconds: int = 3600):
    """
    Run sync_new_records on a schedule. Default: every 1 hour (3600 seconds).
    Perfect for Docker deployment to continuously log new cleaning records.
    """
    from datetime import datetime
    
    hours = interval_seconds / 3600
    print(f"\n{'=' * 60}")
    print("     ROBOROCK CLEANING RECORD SYNC")
    print(f"{'=' * 60}")
    print(f"[SCHEDULE] Checking for new records every {hours:.1f} hour(s)")
    print("[SCHEDULE] Press Ctrl+C to stop\n")
    
    run_count = 0
    
    while True:
        try:
            run_count += 1
            print(f"\n[RUN #{run_count}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            found_new = await sync_new_records()
            
            if found_new:
                print("[SCHEDULE] New records logged to Google Sheets!")
            else:
                print("[SCHEDULE] No new records found")
            
            print(f"[SCHEDULE] Next check in {hours:.1f} hour(s)...")
            await asyncio.sleep(interval_seconds)
            
        except KeyboardInterrupt:
            print("\n[SCHEDULE] Stopping...")
            break
        except Exception as e:
            print(f"[ERROR] Sync error: {e}")
            # Wait before retrying
            await asyncio.sleep(60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Roborock Q8 Data Pipeline")
    parser.add_argument(
        "--mode",
        choices=["monitor", "status", "log", "smart", "schedule", "history", "record_sync"],
        default="smart",
        help="Mode: monitor (continuous), status (one-time), log (manual), smart (detect new), schedule (periodic smart), history (fetch cleaning records), record_sync (hourly new record sync)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3600,
        help="Interval in seconds for schedule/record_sync mode (default: 3600 = 1 hour)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of cleaning records to fetch in history mode (default: 10)"
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
    elif args.mode == "history":
        asyncio.run(fetch_cleaning_history(args.limit))
    elif args.mode == "record_sync":
        asyncio.run(schedule_record_sync(args.interval))
