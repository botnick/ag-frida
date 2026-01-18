import os
import subprocess
import logging
import threading
from core.adb import ADB

logger = logging.getLogger("ag-frida.core.jadx")

class JadxManager:
    """
    Manages interaction with Jadx Decompiler.
    """
    def __init__(self, serial: str):
        self.adb = ADB(serial)
        self.output_dir = os.path.join(os.getcwd(), "dumped_apks")
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def analyze(self, package_name: str):
        """
        1. Find APK path on device.
        2. Pull APK.
        3. Launch Jadx-GUI (Auto-Install if missing).
        """
        try:
            from core.tools_installer import ToolsInstaller
            
            logger.info(f"Analyzing {package_name}...")
            
            # 1. Get Path
            out = self.adb.shell(f"pm path {package_name}")
            if not out or "package:" not in out:
                raise Exception(f"Package {package_name} not found.")
            
            remote_path = out.split("\n")[0].replace("package:", "").strip()
            
            # 2. Pull
            local_name = f"{package_name}.apk"
            local_path = os.path.join(self.output_dir, local_name)
            
            logger.info(f"Pulling {remote_path} -> {local_path}")
            self.adb.pull(remote_path, local_path)
            
            # 3. Launch
            # This will auto-download if missing
            jadx_bin = ToolsInstaller.get_jadx_path()
            
            logger.info(f"Launching {jadx_bin}...")
            # Use Popen to detach
            if os.name == 'nt':
                 # Windows: use shell=True might be needed for .bat
                subprocess.Popen([jadx_bin, local_path], shell=True)
            else:
                subprocess.Popen([jadx_bin, local_path])
                
            return {"status": "launched", "path": local_path}

        except Exception as e:
            logger.error(f"Jadx Analysis Failed: {e}")
            # If it was pulled but jadx failed
            if os.path.exists(os.path.join(self.output_dir, f"{package_name}.apk")):
                 return {"status": "pulled_only", "path": self.output_dir, "message": f"Error launching Jadx: {e}"}
            raise e
