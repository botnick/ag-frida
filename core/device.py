import logging
import questionary
from typing import List, Optional, Dict
from .adb import ADB

logger = logging.getLogger("ag-frida.core.device")

class DeviceManager:
    """
    Manages Android Device Detection and Environment Checks.
    """
    
    def __init__(self):
        self.adb = ADB() # Base ADB generic

    def select_device(self, auto_select: bool = True) -> str:
        """
        Lists devices and prompts user to select one.
        Returns the serial number.
        """
        devices = self.adb.get_devices()
        
        if not devices:
            raise RuntimeError("No Android devices connected.") # Handled in main
            
        # Filter only 'device' state
        ready_devices = [d for d in devices if d[1] == 'device']
        
        if not ready_devices:
            raise RuntimeError("Devices found but unauthorized/offline.")

        if len(ready_devices) == 1 and auto_select:
            serial = ready_devices[0][0]
            logger.info(f"Auto-selected device: [cyan]{serial}[/cyan]", extra={"markup": True})
            return serial

        # Interactive selection
        choices = [f"{d[0]} ({d[1]})" for d in ready_devices]
        selected = questionary.select("Select target device:", choices=choices).ask()
        
        if not selected:
            raise KeyboardInterrupt
            
        return selected.split()[0]

    def get_info(self, serial: str) -> Dict[str, str]:
        """Gets basic info: Arch, SDK, Root status."""
        adb = ADB(serial)
        
        # 1. Architecture
        arch = adb.shell("getprop ro.product.cpu.abi").strip()
        
        # 2. SDK Version
        sdk = adb.shell("getprop ro.build.version.sdk").strip()
        
        # 3. Root Check (Simple)
        is_root = False
        try:
            # Check for su binary or try running 'su -c id'
            su_check = adb.shell("which su", check=False)
            if su_check.strip():
                # Verify we can actually use it
                id_out = adb.shell("su -c id", check=False)
                if "uid=0(root)" in id_out:
                    is_root = True
        except Exception:
            pass

        return {
            "serial": serial,
            "arch": arch,
            "sdk": sdk,
            "rooted": is_root
        }

    def list_packages(self, serial: str, filter_type: str = "all") -> list:
        """
        Lists installed packages.
        filter_type: 'user', 'system', 'all'
        Returns list of package IDs (strings).
        """
        try:
            cmd = "pm list packages"
            if filter_type == "user": cmd += " -3"
            elif filter_type == "system": cmd += " -s"
            
            # Use check=False to avoid raising exception on non-zero exit (e.g. warnings)
            out = ADB(serial).shell(cmd, check=False)
            
            if not out or "package:" not in out:
                return []

            results = []
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("package:"):
                    results.append(line.replace("package:", "").strip())
            return results
        except Exception as e:
            logger.error(f"Error listing packages: {e}")
            return []

    def list_packages_detailed(self, serial: str) -> list:
        """
        Returns [{id, type}] sorted by ID.
        """
        try:
            # 1. Get User Apps (User installed)
            user_pkgs = set(self.list_packages(serial, "user"))
            
            # 2. Get All Apps
            all_pkgs = self.list_packages(serial, "all")
            
            results = []
            for p in all_pkgs:
                if not p: continue
                # If it's in user_pkgs, it's 'user', else 'system'
                p_type = "user" if p in user_pkgs else "system"
                results.append({"id": p, "type": p_type})
                
            # If empty (unexpected), try one more fallback to just 'all' with 'unknown' type
            if not results and all_pkgs:
                 results = [{"id": p, "type": "system"} for p in all_pkgs]

            return sorted(results, key=lambda x: x['id'])
        except Exception as e:
            logger.error(f"Error getting detailed packages: {e}")
            return []
    def list_running_processes(self, serial):
        """
        Returns list of [name, pid]
        """
        adb = ADB(serial)
        # Get Name and PID
        out = adb.shell("ps -A -o NAME,PID", check=False)
        results = []
        for line in out.splitlines():
            line = line.strip()
            if not line or "NAME" in line or "PID" in line: continue
            
            parts = line.split()
            name = parts[0]
            
            # Filter Kernel Threads (usually with brackets)
            if name.startswith("[") and name.endswith("]"): continue
            
            if len(parts) >= 2:
                results.append([name, parts[-1]])
            elif len(parts) == 1:
                 results.append([name, "?"])
                 
        return results
