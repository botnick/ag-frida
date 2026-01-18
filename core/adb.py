import subprocess
import logging
from typing import List, Optional, Tuple
import shutil
from .adb_installer import ADBInstaller

logger = logging.getLogger("ag-frida.core.adb")

class ADB:
    """
    Production-grade ADB Wrapper.
    Handles command execution, error parsing, and device targeting.
    """
    
    def __init__(self, device_id: Optional[str] = None):
        self.device_id = device_id
        # Resolve ADB path dynamically (System or Local)
        self.adb_bin = ADBInstaller.get_adb_path()

    def _build_cmd(self, args: List[str]) -> List[str]:
        cmd = [self.adb_bin]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(args)
        return cmd

    def run(self, args: List[str], check: bool = True) -> str:
        """
        Runs an ADB command and returns stdout.
        Raises subprocess.CalledProcessError if check=True and command fails.
        """
        cmd = self._build_cmd(args)
        # logger.debug(f"Exec: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=check,
                encoding='utf-8',
                errors='replace' # Handle potential encoding issues in logcat/shell
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.debug(f"ADB Error [{e.returncode}]: {e.stderr.strip()}")
            raise e

    def shell(self, command: str, check: bool = True) -> str:
        """Runs a command via adb shell."""
        return self.run(["shell", command], check=check)

    def push(self, local_path: str, remote_path: str) -> None:
        """Pushes a file to the device."""
        self.run(["push", local_path, remote_path])

    def pull(self, remote_path: str, local_path: str) -> None:
        """Pulls a file from the device."""
        self.run(["pull", remote_path, local_path])

    def install(self, apk_path: str) -> None:
        self.run(["install", "-r", apk_path])

    @staticmethod
    def get_devices() -> List[Tuple[str, str]]:
        """
        Returns a list of (serial, status).
        e.g. [('emulator-5554', 'device'), ('RF8...', 'unauthorized')]
        """
        try:
            adb_bin = ADBInstaller.get_adb_path()
            # Use short timeout to prevent hanging if ADB is stuck
            process = subprocess.run(
                [adb_bin, "devices"], 
                capture_output=True, 
                text=True, 
                encoding='utf-8',
                timeout=5
            )
            output = process.stdout
            devices = []
            for line in output.splitlines():
                if line.strip() and "List of devices attached" not in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        devices.append((parts[0], parts[1]))
            return devices
        except subprocess.TimeoutExpired:
            logger.error("ADB Devices timed out.")
            return []
        except Exception as e:
            logger.error(f"Failed to list devices: {e}")
            return []

    def connect(self, host: str, port: int = 5555) -> bool:
        """Connects to a remote device via TCP/IP."""
        try:
            out = self.run(["connect", f"{host}:{port}"])
            if "connected to" in out:
                return True
            return False
        except:
            return False

    def root(self) -> bool:
        """Restarts adb as root."""
        try:
             # This restarts the adbd daemon on the device
             # The command finishes quickly, but the device might reconnect
             self.run(["root"])
             # We assume success if no error, but ideally valid check is 'whoami' later.
             return True
        except:
             return False

    def disconnect(self, host: str, port: int = 5555) -> bool:
        """Disconnects a remote device."""
        try:
            self.run(["disconnect", f"{host}:{port}"])
            return True
        except:
            return False

    def enable_tcpip(self, port: int = 5555):
        """Restarts adbd listening on TCPIP (requires USB first)."""
        self.run(["tcpip", str(port)])

