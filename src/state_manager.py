"""
State Manager for tracking device state between runs.
Uses total_clean_count to detect new cleanings.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional


class StateManager:
    """Manages persistent state to track last known device metrics."""
    
    def __init__(self, state_file: str = "config/last_state.json"):
        self.state_file = Path(state_file)
        self.state: Dict[str, Any] = {}
        self._load()
    
    def _load(self):
        """Load state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    self.state = json.load(f)
                print(f"[STATE] Loaded state from {self.state_file}")
            except Exception as e:
                print(f"[WARN] Could not load state: {e}")
                self.state = {}
        else:
            self.state = {}
            print("[STATE] No previous state found, starting fresh")
    
    def _save(self):
        """Save state to file."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2)
        print(f"[STATE] Saved state to {self.state_file}")
    
    def get_device_state(self, device_name: str) -> Dict[str, Any]:
        """Get last known state for a device."""
        return self.state.get(device_name, {})
    
    def get_last_clean_count(self, device_name: str) -> int:
        """Get the last known total_clean_count for a device."""
        device_state = self.get_device_state(device_name)
        return device_state.get('last_clean_count', 0)
    
    def update_device_state(
        self, 
        device_name: str, 
        clean_count: int,
        total_area: float = None,
        total_time: int = None
    ):
        """Update and save device state."""
        self.state[device_name] = {
            'last_clean_count': clean_count,
            'last_total_area': total_area,
            'last_total_time': total_time,
            'last_updated': datetime.now().isoformat()
        }
        self._save()
    
    def has_new_cleaning(self, device_name: str, current_count: int) -> bool:
        """Check if there's a new cleaning since last check."""
        last_count = self.get_last_clean_count(device_name)
        return current_count > last_count
    
    def get_new_cleaning_count(self, device_name: str, current_count: int) -> int:
        """Get the number of new cleanings since last check."""
        last_count = self.get_last_clean_count(device_name)
        return max(0, current_count - last_count)
