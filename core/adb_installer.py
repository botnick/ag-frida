import os
import sys
import platform
import requests
import zipfile
import shutil
import logging
from rich.console import Console
from rich.progress import Progress

logger = logging.getLogger("ag-frida.core.adb_installer")
console = Console()

class ADBInstaller:
    """
    Manages local installation of Android Platform Tools (ADB).
    Zero-Dependency: Downloads official binaries from Google.
    """
    
    BASE_URL = "https://dl.google.com/android/repository/platform-tools-latest-{}.zip"
    INSTALL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
    
    @staticmethod
    def get_adb_path() -> str:
        """
        Returns path to executable adb. 
        Prioritizes Local > System.
        Auto-installs if neither found.
        """
        system = platform.system().lower()
        exe_name = "adb.exe" if system == "windows" else "adb"
        
        # 1. Check Local (bin/platform-tools/adb)
        local_path = os.path.join(ADBInstaller.INSTALL_DIR, "platform-tools", exe_name)
        if os.path.exists(local_path):
            return local_path
            
        # 2. Check System PATH
        if shutil.which("adb"):
            # If we want to force local, we skip this. But being nice to existing env is good.
            # However, for "Portable", local is better.
            # Let's check if User specifically requested "Portable Mode" via strict check?
            # For now, fallback to system is standard behavior.
            return "adb" 

        # 3. Not found -> Install
        console.print("[yellow]ADB not found in system or local.[/yellow]")
        console.print("[cyan]Auto-downloading Android Platform Tools (Zero-Dependency)...[/cyan]")
        ADBInstaller._install(system)
        
        if os.path.exists(local_path):
            console.print("[green]ADB Installed successfully![/green]")
            return local_path
        else:
            raise RuntimeError("Failed to install ADB.")

    @staticmethod
    def _install(system):
        if not os.path.exists(ADBInstaller.INSTALL_DIR):
            os.makedirs(ADBInstaller.INSTALL_DIR)
            
        os_key = "windows"
        if system == "darwin": os_key = "darwin"
        elif system == "linux": os_key = "linux"
        
        url = ADBInstaller.BASE_URL.format(os_key)
        zip_path = os.path.join(ADBInstaller.INSTALL_DIR, "platform-tools.zip")
        
        # Download
        try:
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                total = int(r.headers.get('content-length', 0))
                with Progress() as progress:
                    task = progress.add_task("Downloading...", total=total)
                    with open(zip_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                            progress.update(task, advance=len(chunk))
                            
            # Extract
            console.print("Extracting...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(ADBInstaller.INSTALL_DIR)
                
            # Cleanup
            os.remove(zip_path)
            
            # MacOS/Linux Permission fix
            if system != "windows":
                adb_bin = os.path.join(ADBInstaller.INSTALL_DIR, "platform-tools", "adb")
                os.chmod(adb_bin, 0o755)
                
        except Exception as e:
            logger.error(f"Install failed: {e}")
            raise
