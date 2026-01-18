from fastapi import FastAPI, WebSocket, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import os
import json

# Import Core
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.device import DeviceManager
from core.codeshare import CodeShare
from web.bridge import WebBridge, log_queue

app = FastAPI(title="ag-frida Web")
bridge = WebBridge.get_instance()

# Templates & Static
base_dir = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(base_dir, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(base_dir, "templates"))

# --- Pydantic Models ---
class StartSessionRequest(BaseModel):
    serial: str
    target: str
    mode: str
    scripts: List[str] = []
    codeshare: List[str] = []
    auto_restart: bool = True

# --- API Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/devices")
def get_devices():
    try:
        dm = DeviceManager()
        # Hacky filtering of ADB output from DeviceManager if needed, 
        # but select_device usually interacts.
        # We need a non-interactive list method in DeviceManager ideally.
        # Let's use ADB direct for raw list.
        from core.adb import ADB
        # DeviceManager.select_device logic is interactive. 
        # We should probably expose list_devices in DeviceManager or ADB.
        # Let's rely on ADB.get_devices()
        return {"devices": ADB.get_devices()}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/apps/{serial}")
def get_apps(serial: str, type: str = "user"):
    try:
        from core.device import DeviceManager
        dm = DeviceManager()
        if type == "running":
            return {"apps": dm.list_running_processes(serial)}
        else:
            return {"apps": dm.list_packages(serial)}
    except Exception as e:
        return {"error": str(e), "apps": []}

@app.get("/api/processes/{serial}")
def get_processes(serial: str):
    try:
        from core.device import DeviceManager
        dm = DeviceManager()
        # Returns list of [name, pid]
        return {"processes": dm.list_running_processes(serial)}
    except Exception as e:
        return {"processes": [], "error": str(e)}

# --- V4.1 Enhancements ---

@app.post("/api/device/connect")
def connect_device(ip: str):
    try:
        from core.adb import ADB
        adb = ADB()
        port = 5555
        if ":" in ip:
            ip, str_port = ip.split(":")
            port = int(str_port)
        
        success = adb.connect(ip, port)
        if success:
            return {"status": "ok", "message": f"Connected to {ip}:{port}"}
        else:
            return {"status": "error", "message": "Connection refused"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/profiles")
def get_profiles():
    try:
        from core.config import ConfigManager
        cm = ConfigManager()
        return {"profiles": cm.load_profiles()}
    except Exception as e:
        return {"profiles": {}, "error": str(e)}

@app.get("/api/scripts")
def get_local_scripts():
    try:
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
        if not os.path.exists(scripts_dir):
            return {"scripts": []}
        
        files = []
        for f in os.listdir(scripts_dir):
            if f.endswith(".js"):
                files.append(f)
        return {"scripts": files}
    except Exception as e:
        return {"scripts": [], "error": str(e)}

@app.get("/api/scripts/{filename}")
def get_script_content(filename: str):
    try:
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
        path = os.path.join(scripts_dir, filename)
        if os.path.exists(path):
             with open(path, 'r', encoding='utf-8') as f:
                 return {"content": f.read()}
        return {"content": ""}
    except Exception as e:
        return {"content": "", "error": str(e)}

@app.get("/api/codeshare/recommended")
def get_recommended_codeshare():
    try:
        from core.codeshare import CodeShare
        return {"recommended": CodeShare.RECOMMENDED_SCRIPTS}
    except Exception as e:
        return {"recommended": [], "error": str(e)}

@app.post("/api/session/start")
def start_session(req: StartSessionRequest):
    try:
        success = bridge.start_session(
            req.serial, 
            req.target, 
            req.mode, 
            req.scripts, 
            req.codeshare, 
            req.auto_restart
        )
        return {"status": "ok" if success else "failed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- V5: AI Assistant Endpoints ---

class AIConfigRequest(BaseModel):
    active_provider: Optional[str] = None
    provider_config: Optional[dict] = None

class AIGenerateRequest(BaseModel):
    prompt: str
    serial: Optional[str] = None 
    package: Optional[str] = None
    role_category: Optional[str] = None
    sub_role: Optional[str] = None

@app.get("/api/ai/config")
def get_ai_config():
    try:
        from core.config import ConfigManager
        cm = ConfigManager()
        ai = cm.get_ai_config()
        
        # Security: Mask API Keys for Frontend
        if 'providers' in ai:
            for prov, data in ai['providers'].items():
                if 'api_key' in data and data['api_key']:
                    data['api_key'] = "********" 
        
        return ai
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/ai/config")
def save_ai_config(req: AIConfigRequest):
    try:
        from core.config import ConfigManager
        cm = ConfigManager()
        
        # New Method: Save specific provider or update active
        cm.save_ai_config(req.active_provider, req.provider_config)
            
        return {"status": "saved"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/ai/test")
def test_ai_connection():
    try:
        from core.config import ConfigManager
        from core.ai import AIAssistant
        cm = ConfigManager()
        cfg = cm.load_full_config().get('ai', {})
        if not cfg: return {"success": False, "error": "No AI config found"}
        
        ai = AIAssistant(cfg)
        return ai.test_connection()
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": f"Server Error: {str(e)}"}

@app.post("/api/ai/generate")
def generate_ai_script(req: AIGenerateRequest):
    try:
        from core.ai import AIAssistant
        from core.config import ConfigManager
        
        cm = ConfigManager()
        # Ensure we have active config
        ai_conf = cm.get_ai_config()
        if not ai_conf.get("active_provider"):
            return {"status": "error", "message": "No active AI provider configured"}
            
        assistant = AIAssistant()
        
        # Determine Context
        context_data = {
            "serial": req.serial,
            "package": req.package
        }
        
        # Generate with specific Role
        script = assistant.generate_script(
            req.prompt, 
            context_data,
            role_category=req.role_category,
            sub_role=req.sub_role
        )
        
        return {"status": "success", "script": script}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/session/stop")
def stop_session(serial: str):
    """Stops the session for a specific device."""
    try:
        success = bridge.stop_session(serial)
        return {"status": "stopped" if success else "not_found", "serial": serial}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/status")
def get_status():
    """Returns list of active device serials."""
    try:
        return {"running_sessions": bridge.get_active_sessions()}
    except Exception as e:
        return {"running_sessions": [], "error": str(e)}

@app.get("/api/magisk/{serial}/status")
def get_magisk_status(serial: str):
    try:
        from core.magisk import MagiskManager
        mm = MagiskManager(serial)
        return mm.check_status()
    except Exception as e:
         return {"installed": False, "error": str(e)}

@app.post("/api/magisk/{serial}/denylist")
def toggle_denylist(serial: str, enable: bool):
    try:
        from core.magisk import MagiskManager
        mm = MagiskManager(serial)
        mm.set_denylist(enable)
        return {"status": "ok", "enabled": enable}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/magisk/{serial}/add")
def add_denylist_target(serial: str, package: str):
    """Adds a package to the Magisk DenyList."""
    try:
        from core.magisk import MagiskManager
        mm = MagiskManager(serial)
        mm.add_target(package)
        return {"status": "ok", "message": f"Added {package} to DenyList"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- Root Automation Endpoints ---

@app.get("/api/root/{serial}/info")
def get_root_device_info(serial: str):
    try:
        from core.root import RootAutomator
        ra = RootAutomator(serial)
        return ra.get_device_info()
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/root/{serial}/partition")
def detect_partition(serial: str):
    try:
        from core.root import RootAutomator
        ra = RootAutomator(serial)
        return ra.find_boot_partition()
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/root/{serial}/dump")
def dump_boot_img(serial: str):
    try:
        from core.root import RootAutomator
        ra = RootAutomator(serial)
        return ra.dump_boot()
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/root/{serial}/install-magisk")
def install_magisk_apk_root(serial: str):
    try:
        from core.root import RootAutomator
        ra = RootAutomator(serial)
        return ra.install_magisk_app()
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/root/{serial}/launch-magisk")
def launch_magisk_app_root(serial: str):
    try:
        from core.root import RootAutomator
        ra = RootAutomator(serial)
        return ra.launch_magisk_app()
    except Exception as e:
        return {"status": "error", "message": str(e)}


# --- V6: Manual Server Management ---

@app.get("/api/server/{serial}/status")
def get_server_status_api(serial: str):
    """
    Returns detailed server status (Installed, Running, Version).
    """
    try:
        from core.server import ServerManager
        sm = ServerManager(serial)
        return sm.get_server_status()
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/server/{serial}/action")
def manage_server_api(serial: str, action: str):
    """
    Actions: start, stop, restart, install
    """
    try:
        from core.server import ServerManager
        sm = ServerManager(serial)
        
        if action == "start":
            sm._start_server()
            return {"status": "ok", "message": "Server started"}
        elif action == "stop":
            sm.kill_server()
            return {"status": "ok", "message": "Server stopped"}
        elif action == "restart":
            sm.kill_server()
            import time
            time.sleep(1)
            sm._start_server()
            return {"status": "ok", "message": "Server restarted"}
        elif action == "install":
            # Force re-install
            sm.ensure_server(force_check=True)
            return {"status": "ok", "message": "Server installed/updated"}
            
        return {"status": "error", "message": "Invalid action"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- V7: JADX Analysis Endpoint ---
@app.post("/api/tools/jadx/{device_id}")
def analyze_with_jadx(device_id: str, package: str):
    """Pulls APK from device and analyzes with JADX."""
    try:
        from core.jadx import JadxManager
        analyzer = JadxManager(device_id)
        result = analyzer.analyze(package)
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- WebSocket for Logs (Throttled) ---
@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    buffer = []
    MAX_BATCH = 50
    FLUSH_INTERVAL = 0.1 # 100ms
    
    try:
        while True:
            # Collect logs
            try:
                # Drain queue up to limit
                while not log_queue.empty() and len(buffer) < MAX_BATCH:
                    buffer.append(log_queue.get_nowait())
            except: 
                pass
            
            # Send if we have data
            if buffer:
                # Send as JSON array implies frontend handles it
                # Or join with \n to keep it simple text
                payload = "\n".join(buffer)
                await websocket.send_text(payload)
                buffer.clear()
            
            await asyncio.sleep(FLUSH_INTERVAL)
            
    except asyncio.CancelledError:
        # Expected processing on server shutdown
        pass
    except Exception:
        pass
