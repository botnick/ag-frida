import os
import sys
import platform
import requests
import zipfile
import shutil
import logging
from rich.console import Console
from rich.progress import Progress

logger = logging.getLogger("ag-frida.core.tools_installer")
console = Console()

class ToolsInstaller:
    """
    Manages local installation of external tools (Jadx, etc.).
    """
    
    BIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
    JADX_VERSION = "1.5.3" # Latest Stable version
    JADX_URL = f"https://github.com/skylot/jadx/releases/download/v{JADX_VERSION}/jadx-{JADX_VERSION}.zip"
    
    @staticmethod
    def get_jadx_path() -> str:
        """
        Returns path to jadx-gui executable.
        Auto-installs if not found.
        """
        system = platform.system().lower()
        is_win = system == "windows"
        exe_name = "jadx-gui.bat" if is_win else "jadx-gui"
        
        # Check Local
        jadx_dir = os.path.join(ToolsInstaller.BIN_DIR, "jadx")
        jadx_bin = os.path.join(jadx_dir, "bin", exe_name)
        
        if os.path.exists(jadx_bin):
            return jadx_bin
            
        # Check System PATH (only if we trust it, but we prefer local to be 100% sure it works for user)
        if shutil.which("jadx-gui"):
            return "jadx-gui"

        # Not found -> Install
        console.print(f"[yellow]Jadx-GUI not found.[/yellow]")
        console.print(f"[cyan]Auto-downloading Jadx v{ToolsInstaller.JADX_VERSION}...[/cyan]")
        ToolsInstaller._install_jadx(jadx_dir)
        
        if os.path.exists(jadx_bin):
            # Fix permissions on unix
            if not is_win:
                os.chmod(jadx_bin, 0o755)
            console.print("[green]Jadx Installed successfully![/green]")
            return jadx_bin
        else:
            raise RuntimeError("Failed to install Jadx.")

    @staticmethod
    def _install_jadx(dest_dir):
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
            
        zip_path = os.path.join(ToolsInstaller.BIN_DIR, "jadx.zip")
        
        try:
            # Download
            with requests.get(ToolsInstaller.JADX_URL, stream=True) as r:
                r.raise_for_status()
                total = int(r.headers.get('content-length', 0))
                with Progress() as progress:
                    task = progress.add_task("Downloading Jadx...", total=total)
                    with open(zip_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                            progress.update(task, advance=len(chunk))
                            
            # Extract
            console.print("Extracting Jadx...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(dest_dir)
                
        except Exception as e:
            logger.error(f"Failed to install Jadx: {e}")
            # cleanup
            if os.path.exists(dest_dir): shutil.rmtree(dest_dir)
            raise e
        finally:
            if os.path.exists(zip_path):
                os.remove(zip_path)
