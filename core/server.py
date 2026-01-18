import os
import requests
import frida
import lzma
import logging
import time
from typing import Optional
from rich.console import Console
from .adb import ADB
from .device import DeviceManager

logger = logging.getLogger("ag-frida.core.server")
console = Console()

class ServerManager:
    """
    Manages frida-server lifecycle: Check, Download, Install, Start.
    """
    
    GITHUB_API = "https://api.github.com/repos/frida/frida/releases/tags/{}"
    CACHE_DIR = os.path.expanduser("~/.ag-frida/cache")

    def __init__(self, device_serial: str):
        self.adb = ADB(device_serial)
        self.device_mgr = DeviceManager()
        self.serial = device_serial
        self.arch = None # Will be set in ensure_server

    def _get_server_name(self):
        """
        DYNAMIC PRO: Generates a stealthy, system-like process name.
        Avoids 'frida-server' to bypass simple anti-frida checks.
        """
        # List of "safe" looking names
        STEALTH_NAMES = [
            "ksystem_server",
            "android.process.media.v2",
            "google.play.service.updater",
            "com.android.support.v4",
            "system_server_background",
            "log_demon_v1"
        ]
        
        # We need persistence for this to recognize our own server
        # For this "Pro" implementation, we'll hash the device serial to pick a consistent name 
        # for THIS device, but random across devices. This ensures we don't re-upload/restart constantly.
        import hashlib
        hash_idx = int(hashlib.sha256(self.serial.encode()).hexdigest(), 16) % len(STEALTH_NAMES)
        
        # Suffix with arch for technical correctness in managing binaries
        # But for the Process Name (argv[0]), we want the clean name.
        # This function returns the BINARY FILENAME on disk.
        base_name = STEALTH_NAMES[hash_idx]
        if self.arch:
            return f"{base_name}-{self.arch}"
        return f"{base_name}"

    def _get_remote_path(self):
        return f"/data/local/tmp/{self._get_server_name()}"

    def get_server_status(self) -> dict:
        """
        Returns detailed status of the frida-server.
        """
        status = {
            "rooted": False,
            "installed": False,
            "running": False,
            "version": None,
            "target_version": frida.__version__,
            "compatible": False,
            "arch": None
        }
        
        try:
            info = self.device_mgr.get_info(self.serial)
            status["rooted"] = info['rooted']
            status["arch"] = info['arch']
            
            if not status["rooted"]:
                return status

            # Check Remote Version
            remote_ver = self._get_remote_version()
            if remote_ver:
                status["installed"] = True
                status["version"] = remote_ver
                status["compatible"] = (remote_ver == status["target_version"])
            
            # Check Running
            # Check for both standard and stealth names
            status["running"] = self._is_server_process_running()
            
        except Exception as e:
            logger.error(f"Status check failed: {e}")
            
        return status

    def ensure_server(self, force_check: bool = False, port: Optional[int] = None):
        """
        Main orchestration method to ensure server is running and matches version.
        """
        # 1. Check Root (Requirement for server setup)
        info = self.device_mgr.get_info(self.serial)
        if not info['rooted']:
            logger.warning("Device is NOT rooted. Skipping server setup. "
                           "Ensure you are using a Gadget or Debuggable app.")
            return

        target_version = frida.__version__
        arch = info['arch']
        
        logger.info(f"Checking frida-server... (Target: {target_version}, Arch: {arch})")

        # 2. Check if running
        try:
            # Simple check: ps | grep frida-server
            # or try connecting via frida
            d = frida.get_device(id=self.serial)
            # If we can connect and list processes, it's running.
            # But we need Version check.
            # Currently frida-python doesn't easily give remote server version without connect.
            # We can run `frida-server --version` on device.
            pass
        except:
            pass
            
        # Check binary existence and version on disk
        remote_version = self._get_remote_version()
        
        if remote_version == target_version:
            logger.info("Server version matches.")
            # Verify running
            if not self._is_server_process_running():
                logger.info("Server present but not running. Starting...")
                self._start_server()
            else:
                logger.info("Server is already running.")
                if port and not self._is_server_process_running(self._get_server_name(), port): # Check if stealth server with port is running
                    logger.info(f"Standard server running, but stealth server on port {port} requested. Restarting.")
                    self.start_stealth_server(port)
        else:
            console.print(f"[yellow]Version Mismatch/Missing! Local: {target_version}, Remote: {remote_version}[/yellow]")
            console.print("[cyan]Auto-downloading & Installing...[/cyan]")
            
            # Kill if running
            self.kill_server()
                
            # Download & Install
            local_bin = self._download_server(target_version, arch)
            self._install_server(local_bin)
            
            if port:
                self.start_stealth_server(port)
            else:
                self._start_server()

    def _get_remote_version(self) -> str:
        try:
            # Attempt to run it to get version
            remote_path = self._get_remote_path()
            out = self.adb.shell(f"{remote_path} --version", check=False)
            return out.strip()
        except Exception as e:
            logger.debug(f"Could not get remote server version: {e}")
            return None

    def _is_server_process_running(self, name: Optional[str] = None, port: Optional[int] = None) -> bool:
        """
        Checks if a frida-server process is running.
        Can check for a specific name or port.
        SMART CONNECT: Checks for both 'frida-server' and 'fs-{arch}'.
        """
        candidates = []
        if name:
            candidates.append(name)
        else:
            candidates.append(self._get_server_name()) # fs-{arch}
            candidates.append("frida-server") # Standard
        
        try:
            # 1. Broad Process Check
            # We check for all candidates in one go
            cmd = "ps -A"
            out = self.adb.shell(cmd, check=False)
            
            for cand in candidates:
                if cand in out:
                    # Found a candidate!
                    if port:
                        # 2. Port Verification for this candidate
                        if f":{port}" in out: return True # Simple check
                        
                        # Netstat check
                        try:
                            ns_check = self.adb.shell(f"netstat -tunlp | grep :{port}", check=False)
                            if f":{port}" in ns_check and "LISTEN" in ns_check: return True
                        except: pass
                        
                        return False # Name found but port not confirmed
                    return True
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking if server process is running: {e}")
            return False

    def kill_server(self):
        """Kills the running frida-server process."""
        name = self._get_server_name()
        logger.info(f"Killing {name}...")
        try:
            # Try pkill first
            self.adb.shell(f"pkill -f {name}", check=False)
            
            # Fallback: manual PID search & kill
            # This handles cases where pkill is missing (older Android)
            cmd = f"ps -A | grep {name}"
            out = self.adb.shell(cmd, check=False)
            for line in out.splitlines():
                if name in line:
                    parts = line.split()
                    if len(parts) > 1:
                        pid = parts[1] # Usually PID is 2nd col
                        self.adb.shell(f"kill -9 {pid}", check=False)
        except Exception as e:
            logger.debug(f"Kill server error (ignored): {e}")

    def _download_server(self, version: str, arch: str) -> str:
        """Downloads xz, extracts, returns path to binary."""
        
        # Mapping Android Arch to Frida filenames
        # arm64-v8a -> arm64
        # armeabi-v7a -> arm
        # x86_64 -> x86_64
        # x86 -> x86
        frida_arch = arch
        if "arm64" in arch: frida_arch = "android-arm64"
        elif "arm" in arch: frida_arch = "android-arm"
        elif "x86_64" in arch: frida_arch = "android-x86_64"
        elif "x86" in arch: frida_arch = "android-x86"
        
        filename = f"frida-server-{version}-{frida_arch}.xz"
        
        # Ensure Cache
        if not os.path.exists(self.CACHE_DIR):
            os.makedirs(self.CACHE_DIR)
            
        cache_path = os.path.join(self.CACHE_DIR, filename)
        bin_path = cache_path.replace(".xz", "")

        # Check Cache
        if os.path.exists(bin_path):
            logger.info("Using cached binary.")
            return bin_path

        # Download
        url = f"https://github.com/frida/frida/releases/download/{version}/{filename}"
        logger.info(f"Downloading: {url}")
        
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(cache_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        # Extract
        logger.info("Extracting...")
        with lzma.open(cache_path) as f_in:
            with open(bin_path, 'wb') as f_out:
                f_out.write(f_in.read())
                
        return bin_path

    def _install_server(self, local_path):
        remote_path = self._get_remote_path()
        logger.info(f"Pushing to {remote_path}...")
        self.adb.push(local_path, remote_path)
        self.adb.shell(f"chmod 755 {remote_path}")

    def _start_server(self):
        logger.info("Starting frida-server in background...")
        
        # FIX: Common Permission Issues (SELinux)
        try:
            self.adb.shell("su -c setenforce 0", check=False)
        except:
            pass

        # nohup is tricky on Android sometimes, usually simple background & works
        # Using a specific command to detach properly
        remote_path = self._get_remote_path()
        # Force Root
        cmd = f"su -c 'nohup {remote_path} > /dev/null 2>&1 &'"
        self.adb.shell(cmd)
        time.sleep(2) # Wait for it to spin up

    def start_stealth_server(self, port: int):
        """
        Starts the frida-server listening on a specific port (stealth mode).
        Robust implementation with retry loop and verification.
        """
        logger.info(f"Starting stealth frida-server on port {port}...")
        
        # 1. Check Port Availability
        if self._is_server_process_running(port=port):
             logger.warning(f"Port {port} already in use. Aborting to avoid collateral damage.")
             raise RuntimeError(f"Port {port} is busy") 
             
             # Note: We DO NOT call kill_server() here anymore because it kills BY NAME
             # and would wipe out other valid sessions. The caller (Bridge) should pick a new port. 
        
        # 2. Ensure SELinux is permissive
        try:
            self.adb.shell("su -c setenforce 0", check=False)
        except:
            pass

        remote_path = self._get_remote_path()
        # Command to start on specific port (Stealth) with ROOT privileges
        final_cmd = f"su -c 'nohup {remote_path} -l 0.0.0.0:{port} > /dev/null 2>&1 &'"
        
        self.adb.shell(final_cmd)
        
        # 3. Robust Wait Loop
        logger.info("Waiting for stealth server to bind...")
        for i in range(20): # Wait up to 10 seconds (20 * 0.5)
            if self._is_server_process_running(port=port):
                 logger.info(f"Stealth server successfully started and bound to port {port}")
                 return
            time.sleep(0.5)
            
        # If we get here, it failed
        raise RuntimeError(f"Failed to start stealth server on port {port} (Timeout)")
