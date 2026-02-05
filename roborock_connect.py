"""
Roborock Q8 Connection Script
This script allows you to connect to your Roborock Q8 device and read its data.
"""

import asyncio
import sys
import os
from dotenv import load_dotenv
from roborock.web_api import RoborockApiClient
from roborock.devices.device_manager import create_device_manager, UserParams

# Fix Windows asyncio compatibility issue with Python 3.8+
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Load environment variables
load_dotenv()

# User credentials from environment
EMAIL_ADDRESS = os.getenv("ROBOROCK_EMAIL")

if not EMAIL_ADDRESS:
    raise ValueError("ROBOROCK_EMAIL environment variable is not set. "
                     "Create a .env file with ROBOROCK_EMAIL=your-email@example.com")


async def login_and_get_devices():
    """
    Log in to Roborock account and list devices.
    """
    print(f"[INFO] Email address: {EMAIL_ADDRESS}")
    
    # Create Web API client
    web_api = RoborockApiClient(username=EMAIL_ADDRESS)
    
    # Request verification code (sent to email)
    print("[INFO] Sending verification code to your email...")
    await web_api.request_code()
    
    # Prompt user for code
    code = input("Enter the verification code from your email: ")
    
    # Log in with code
    print("[INFO] Logging in...")
    user_data = await web_api.code_login(code)
    print("[INFO] Login successful!")
    
    return web_api, user_data


async def get_device_info(user_data):
    """
    Get and display device information.
    """
    # Create device manager
    user_params = UserParams(username=EMAIL_ADDRESS, user_data=user_data)
    device_manager = await create_device_manager(user_params)
    
    # List devices
    devices = await device_manager.get_devices()
    
    print(f"\n[INFO] Found {len(devices)} device(s).\n")
    print("=" * 60)
    
    for i, device in enumerate(devices, 1):
        print(f"\n--- Device {i} ---")
        print(f"Device Info: {device}")
        
        # V1 Properties (for standard vacuums)
        if device.v1_properties:
            print("\n[V1 Protocol - Vacuum Properties]")
            
            # Get status information
            status_trait = device.v1_properties.status
            await status_trait.refresh()
            print(f"  Status: {status_trait}")
            
            # Get consumables info if available
            if hasattr(device.v1_properties, 'consumables'):
                consumables = device.v1_properties.consumables
                await consumables.refresh()
                print(f"  Consumables: {consumables}")
            
            # Get battery status if available
            if hasattr(status_trait, 'battery'):
                print(f"  Battery: {status_trait.battery}%")
            
        # A01 Properties (for wet/dry vacuums)
        if hasattr(device, 'a01_properties') and device.a01_properties:
            print("\n[A01 Protocol - Wet/Dry Vacuum Properties]")
            values = await device.a01_properties.query_values()
            print(f"  Values: {values}")
    
    print("\n" + "=" * 60)
    return devices


async def get_detailed_status(device):
    """
    Get detailed status of a specific device.
    """
    if not device.v1_properties:
        print("This device does not support V1 protocol.")
        return None
    
    status_trait = device.v1_properties.status
    await status_trait.refresh()
    
    status_info = {
        "status": str(status_trait),
    }
    
    # Check and add available properties
    if hasattr(status_trait, 'state'):
        status_info["state"] = status_trait.state
    if hasattr(status_trait, 'battery'):
        status_info["battery"] = status_trait.battery
    if hasattr(status_trait, 'clean_time'):
        status_info["clean_time"] = status_trait.clean_time
    if hasattr(status_trait, 'clean_area'):
        status_info["clean_area"] = status_trait.clean_area
    if hasattr(status_trait, 'error_code'):
        status_info["error_code"] = status_trait.error_code
    if hasattr(status_trait, 'fan_power'):
        status_info["fan_power"] = status_trait.fan_power
    if hasattr(status_trait, 'water_box_status'):
        status_info["water_tank"] = status_trait.water_box_status
    if hasattr(status_trait, 'mop_mode'):
        status_info["mop_mode"] = status_trait.mop_mode
    
    return status_info


async def send_command(device, command_type):
    """
    Send command to device.
    
    Command types:
    - start: Start cleaning
    - stop: Stop cleaning
    - pause: Pause cleaning
    - home: Return to dock
    """
    if not device.v1_properties:
        print("This device does not support commands.")
        return False
    
    command_trait = device.v1_properties.command
    
    if command_type == "start":
        await command_trait.start()
        print("Cleaning started!")
    elif command_type == "stop":
        await command_trait.stop()
        print("Cleaning stopped!")
    elif command_type == "pause":
        await command_trait.pause()
        print("Cleaning paused!")
    elif command_type == "home":
        await command_trait.home()
        print("Device sent to dock!")
    else:
        print(f"Unknown command: {command_type}")
        return False
    
    return True


async def main():
    """
    Main function - Connect to device and display information.
    """
    print("\n" + "=" * 60)
    print("       ROBOROCK Q8 CONNECTION SYSTEM")
    print("=" * 60 + "\n")
    
    try:
        # Log in
        web_api, user_data = await login_and_get_devices()
        
        # Get device information
        devices = await get_device_info(user_data)
        
        if devices:
            # Interactive mode
            while True:
                print("\n[MENU]")
                print("1. Show device status")
                print("2. Start cleaning")
                print("3. Stop cleaning")
                print("4. Return to dock")
                print("5. Refresh device list")
                print("0. Exit")
                
                choice = input("\nYour choice: ")
                
                if choice == "0":
                    print("Exiting...")
                    break
                elif choice == "1":
                    for device in devices:
                        if device.v1_properties:
                            status = await get_detailed_status(device)
                            print(f"\nDetailed Status: {status}")
                elif choice == "2":
                    for device in devices:
                        await send_command(device, "start")
                elif choice == "3":
                    for device in devices:
                        await send_command(device, "stop")
                elif choice == "4":
                    for device in devices:
                        await send_command(device, "home")
                elif choice == "5":
                    devices = await get_device_info(user_data)
                else:
                    print("Invalid choice!")
                    
    except Exception as e:
        print(f"\n[ERROR] An error occurred: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
