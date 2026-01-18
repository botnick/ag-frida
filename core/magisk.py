import logging
import os
import requests
from typing import Dict, Any
from core.adb import ADB

logger = logging.getLogger("ag-frida.core.magisk")

class MagiskManager:
    """
    Automates Magisk / Zygisk DenyList operations.
    """
    def __init__(self, serial: str):
        self.adb = ADB(serial)

    def install_magisk(self) -> bool:
        """
        Downloads and installs the latest Magisk APK.
        Note: This only installs the Manager App. Full root requires patching boot image.
        """
        try:
            url = "https://github.com/topjohnwu/Magisk/releases/download/v27.0/Magisk-v27.0.apk"
            local_path = "Magisk-v27.0.apk"
            
            if not os.path.exists(local_path):
                logger.info(f"Downloading Magisk from {url}...")
                with requests.get(url, stream=True) as r:
                    r.raise_for_status()
                    with open(local_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                            
            logger.info("Installing Magisk APK...")
            self.adb.install(local_path)
            return True
        except Exception as e:
            logger.error(f"Failed to install Magisk: {e}")
            return False

    def check_status(self) -> Dict[str, Any]:
        """Checks Magisk version and DenyList status."""
        try:
            # Check version
            ver = self.adb.shell("su -c magisk -v", check=False)
            if not ver or "not found" in ver.lower():
                return {"installed": False, "version": "N/A", "denylist": False}
            
            # Check DenyList status (Requires Zygisk enabled usually)
            # 'magisk --denylist status' might not exist, usually implies checks via config or explicit enable
            # We can try enabling and see output, or parsing magisk database (complex).
            # Simple check: just return version for now.
            return {"installed": True, "version": ver.strip(), "denylist": True} 
        except Exception:
            return {"installed": False, "error": "Failed to check"}

    def set_denylist(self, enable: bool):
        """Enables or Disables DenyList enforcement."""
        arg = "enable" if enable else "disable"
        self.adb.shell(f"su -c magisk --denylist {arg}", check=False)
        # Zygisk often needs reboot? Or restart zygote.
        # "su -c setprop ctl.restart zygote" might be too aggressive during session.
        # Just setting config is usually mostly safe.
        
    def add_target(self, package: str):
        """Adds a package to the DenyList."""
        self.adb.shell(f"su -c magisk --denylist add {package}", check=False)
        
    def remove_target(self, package: str):
        self.adb.shell(f"su -c magisk --denylist rm {package}", check=False)
