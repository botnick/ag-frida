from mcp.server.fastmcp import FastMCP
from typing import List
from core.device import DeviceManager
from core.adb import ADB
from core.jadx import JadxManager

# Create MCP Server
mcp = FastMCP("ag-frida", dependencies=["frida-tools", "adb"])

@mcp.tool()
def list_devices() -> List[str]:
    """Lists connected ADB devices (Serial IDs)."""
    dm = DeviceManager()
    return [d.id for d in dm.enumerate()]

@mcp.tool()
def adb_shell(serial: str, command: str) -> str:
    """Runs a raw ADB shell command on the target device."""
    return ADB(serial).shell(command)

@mcp.tool()
def list_installed_packages(serial: str, filter: str = "user") -> List[str]:
    """Lists installed packages. Filter: 'user', 'system', 'all'."""
    dm = DeviceManager()
    return dm.list_packages(serial, filter)

@mcp.tool()
def analyze_apk_with_jadx(serial: str, package: str) -> str:
    """Pulls APK and opens it in Jadx-GUI locally."""
    jm = JadxManager(serial)
    try:
        res = jm.analyze(package)
        return f"Result: {res}"
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    # Start the MCP server (Stdio by default)
    mcp.run()
