"""
Roborock Data Collector Module
Extracts cleaning metrics and device data from Roborock Q8
"""

import asyncio
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

from roborock.web_api import RoborockApiClient
from roborock.devices.device_manager import create_device_manager, UserParams


@dataclass
class CleaningRecord:
    """Data class for a single cleaning session"""
    timestamp: str
    device_name: str
    clean_time_minutes: int
    clean_area_sqm: float
    battery_start: Optional[int]
    battery_end: Optional[int]
    fan_power: Optional[str]
    water_level: Optional[str]
    mop_mode: Optional[str]
    state: str
    error_code: Optional[int]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_row(self) -> List[Any]:
        """Convert to list for Google Sheets row"""
        return [
            self.timestamp,
            self.device_name,
            self.clean_time_minutes,
            self.clean_area_sqm,
            self.battery_start,
            self.battery_end,
            self.fan_power,
            self.water_level,
            self.mop_mode,
            self.state,
            self.error_code
        ]


@dataclass
class DeviceStatus:
    """Data class for current device status"""
    timestamp: str
    device_name: str
    state: str
    battery: int
    fan_power: Optional[str]
    water_box_status: Optional[int]
    mop_mode: Optional[str]
    error_code: Optional[int]
    clean_time: int
    clean_area: float
    
    def to_row(self) -> List[Any]:
        return [
            self.timestamp,
            self.device_name,
            self.state,
            self.battery,
            self.fan_power,
            self.water_box_status,
            self.mop_mode,
            self.error_code,
            self.clean_time,
            self.clean_area
        ]


class RoborockDataCollector:
    """
    Collects data from Roborock devices via the cloud API.
    """
    
    def __init__(self, email: str):
        self.email = email
        self.web_api = RoborockApiClient(username=email)  # Create once
        self.user_data = None
        self.base_url = None
        self.device_manager = None
        self.devices = []
        self._is_authenticated = False
        
    async def authenticate(self, code: str) -> bool:
        """
        Authenticate with Roborock cloud using verification code.
        """
        try:
            # Use the same web_api instance that requested the code
            self.user_data = await self.web_api.code_login(code)
            self.base_url = await self.web_api.base_url
            self._is_authenticated = True
            print(f"[INFO] Successfully authenticated as {self.email}")
            return True
        except Exception as e:
            print(f"[ERROR] Authentication failed: {e}")
            return False
    
    async def request_verification_code(self) -> bool:
        """
        Request a verification code to be sent to the registered email.
        """
        try:
            # Use existing web_api instance
            await self.web_api.request_code()
            print(f"[INFO] Verification code sent to {self.email}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to request code: {e}")
            return False
    
    async def discover_devices(self) -> List[Any]:
        """
        Discover all Roborock devices on the account.
        """
        if not self._is_authenticated:
            raise Exception("Not authenticated. Call authenticate() first.")
        
        user_params = UserParams(
            username=self.email, 
            user_data=self.user_data,
            base_url=self.base_url
        )
        self.device_manager = await create_device_manager(user_params)
        self.devices = await self.device_manager.get_devices()
        
        print(f"[INFO] Found {len(self.devices)} device(s)")
        return self.devices
    
    async def get_device_status(self, device) -> Optional[DeviceStatus]:
        """
        Get current status of a device.
        """
        if not device.v1_properties:
            print(f"[WARN] Device does not support V1 protocol")
            return None
        
        try:
            status_trait = device.v1_properties.status
            await status_trait.refresh()
            
            # Extract status values with safe defaults
            state = getattr(status_trait, 'state', 'unknown')
            if hasattr(state, 'name'):
                state = state.name
            elif hasattr(state, 'value'):
                state = str(state.value)
            else:
                state = str(state)
            
            battery = getattr(status_trait, 'battery', 0)
            fan_power = getattr(status_trait, 'fan_power', None)
            if fan_power and hasattr(fan_power, 'name'):
                fan_power = fan_power.name
            
            water_box = getattr(status_trait, 'water_box_status', None)
            mop_mode = getattr(status_trait, 'mop_mode', None)
            if mop_mode and hasattr(mop_mode, 'name'):
                mop_mode = mop_mode.name
            
            error_code = getattr(status_trait, 'error_code', None)
            clean_time = getattr(status_trait, 'clean_time', 0) or 0
            clean_area = getattr(status_trait, 'clean_area', 0) or 0
            
            # Convert clean_area from cm² to m²
            clean_area_sqm = round(clean_area / 10000, 2)
            
            device_name = getattr(device, 'name', 'Roborock Q8')
            
            return DeviceStatus(
                timestamp=datetime.now().isoformat(),
                device_name=str(device_name),
                state=state,
                battery=battery,
                fan_power=str(fan_power) if fan_power else None,
                water_box_status=water_box,
                mop_mode=str(mop_mode) if mop_mode else None,
                error_code=error_code,
                clean_time=clean_time,
                clean_area=clean_area_sqm
            )
            
        except Exception as e:
            print(f"[ERROR] Failed to get device status: {e}")
            return None
    
    async def get_all_device_statuses(self) -> List[DeviceStatus]:
        """
        Get status for all discovered devices.
        """
        statuses = []
        for device in self.devices:
            status = await self.get_device_status(device)
            if status:
                statuses.append(status)
        return statuses
    
    def is_cleaning(self, status: DeviceStatus) -> bool:
        """
        Check if device is currently cleaning.
        """
        cleaning_states = ['cleaning', 'segment_cleaning', 'zone_cleaning', 
                          'spot_cleaning', 'Cleaning', 'SegmentCleaning']
        return status.state.lower() in [s.lower() for s in cleaning_states]
    
    def is_idle(self, status: DeviceStatus) -> bool:
        """
        Check if device is idle/charging.
        """
        idle_states = ['charger', 'idle', 'charging', 'paused', 'Charger', 'Idle']
        return status.state.lower() in [s.lower() for s in idle_states]
    
    async def create_cleaning_record(
        self, 
        device,
        battery_start: Optional[int] = None
    ) -> Optional[CleaningRecord]:
        """
        Create a cleaning record from current device status.
        """
        status = await self.get_device_status(device)
        if not status:
            return None
        
        device_name = getattr(device, 'name', 'Roborock Q8')
        
        return CleaningRecord(
            timestamp=datetime.now().isoformat(),
            device_name=str(device_name),
            clean_time_minutes=status.clean_time,
            clean_area_sqm=status.clean_area,
            battery_start=battery_start,
            battery_end=status.battery,
            fan_power=status.fan_power,
            water_level=str(status.water_box_status) if status.water_box_status else None,
            mop_mode=status.mop_mode,
            state=status.state,
            error_code=status.error_code
        )


# Column headers for Google Sheets
CLEANING_HISTORY_HEADERS = [
    "Timestamp",
    "Device Name", 
    "Clean Time (min)",
    "Clean Area (m²)",
    "Battery Start (%)",
    "Battery End (%)",
    "Fan Power",
    "Water Level",
    "Mop Mode",
    "State",
    "Error Code"
]

DEVICE_STATUS_HEADERS = [
    "Timestamp",
    "Device Name",
    "State",
    "Battery (%)",
    "Fan Power",
    "Water Box Status",
    "Mop Mode",
    "Error Code",
    "Clean Time (min)",
    "Clean Area (m²)"
]
