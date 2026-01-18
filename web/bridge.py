import threading
import queue
import logging
import asyncio
from typing import List, Callable, Dict
from core.session import SessionManager
from core.codeshare import CodeShare

# Queue for WebSocket logs
log_queue = queue.Queue()

class QueueHandler(logging.Handler):
    """Custom Log Handler to push logs to queue for WebSockets."""
    def emit(self, record):
        try:
            msg = self.format(record)
            # ARCHITECT-ZERO: Memory Safety Cap
            # Prevent infinite growth if WS client is slow/dead
            if log_queue.qsize() < 1000:
                log_queue.put(msg)
            else:
                # Drop log, or maybe pop one? 
                # Queue is thread-safe, direct access is tricky.
                # Just drop to protect memory.
                pass 
        except Exception:
            self.handleError(record)

# Attach handler to root logger
q_handler = QueueHandler()
q_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S'))
logging.getLogger("ag-frida").addHandler(q_handler)

class WebBridge:
    """
    Singleton Bridge managing a POOL of sessions (Device Farm).
    """
    _instance = None
    
    def __init__(self):
        # Dict[serial, Dict]
        # { 'serial': { 'thread': Thread, 'manager': SessionManager, 'stop': Event } }
        self.sessions: Dict[str, Dict] = {}
        self.lock = threading.Lock() # Thread-safe ops

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def start_session(self, serial: str, target: str, mode: str, scripts: List[str], use_codeshare: List[str], auto_restart: bool):
        with self.lock:
            if serial in self.sessions:
                self.stop_session(serial)
        
        stop_event = threading.Event()
        
        # Prepare Script Loader (Dynamic)
        codeshare = CodeShare()
        def script_loader():
            contents = []
            # Raw scripts
            for s in scripts: contents.append(s)
            # Codeshare
            for slug in use_codeshare:
                c = codeshare.fetch(slug)
                if c: contents.append(c)
            return contents

        def run_thread(stop_ev):
            manager = None
            port = 0
            
            try:
                # Stealth / Random Port Logic (Restored & Robustified)
                import random
                from core.server import ServerManager
                from core.adb import ADB
                
                # Setup ADB & Server
                adb = ADB(serial)
                sm = ServerManager(serial)
                
                # STRICT MANAGER vs WORKER SEPARATION
                # We DO NOT auto-start the server here. The user must use the Manager.
                if not sm._is_server_process_running():
                    raise RuntimeError("Frida Server is NOT running. Please Start Server first!")
                
                # sm.ensure_server() # REMOVED
                
                logging.getLogger("ag-frida").info(f"[{serial}] Starting session via CLI Bridge...")
                
                # Import CLI Bridge
                from core.cli_bridge import CLIBridge
                bridge = CLIBridge(serial)
                bridge.stop_event = stop_ev # Share stop event with bridge
                
                # Script Loader Wrapper
                current_scripts = script_loader()
                
                # Use local variable to avoid UnboundLocalError due to scoping
                current_mode = mode
                current_target = target

                # Attach Mode Resolution Logic (Same as main.py)
                if current_mode == "attach":
                    try:
                        from core.session import SessionManager
                        temp_sm = SessionManager(serial)
                        # Reuse the helper from SessionManager
                        resolved_pid = temp_sm._resolve_pid_from_pkg(current_target)
                        if resolved_pid:
                            logging.getLogger("ag-frida").info(f"[{serial}] Resolved '{current_target}' -> PID {resolved_pid}")
                            current_target = str(resolved_pid)
                        else:
                            logging.getLogger("ag-frida").warning(f"[{serial}] Could not resolve '{current_target}'. Attempting Spawn fallback...")
                            current_mode = "spawn"
                    except Exception as re:
                         logging.getLogger("ag-frida").warning(f"PID Resolution Error: {re}")

                # Output Callback for WebSockets
                def bridge_callback(msg, data):
                    # Format log for Web UI
                    if isinstance(msg, dict) and "payload" in msg:
                        entry = f"[{serial}] {msg['payload']}"
                        logging.getLogger("ag-frida").info(entry)
                    else:
                        logging.getLogger("ag-frida").info(f"[{serial}] {msg}")

                # Run CLI Bridge
                bridge.run(current_target, current_mode, current_scripts, auto_restart=auto_restart, on_message=bridge_callback)
                
            except Exception as e:
                logging.getLogger("ag-frida").error(f"[{serial}] Web Session Failed: {e}")
            finally:
                logging.getLogger("ag-frida").info(f"[{serial}] Session Stopped.")

        thread = threading.Thread(target=run_thread, args=(stop_event,), daemon=True)
         
        with self.lock:
            self.sessions[serial] = {
                "thread": thread,
                "stop_event": stop_event,
                "target": target
            }
        
        thread.start()
        return True

    def stop_session(self, serial: str):
        with self.lock:
            if serial in self.sessions:
                sess = self.sessions[serial]
                sess["stop_event"].set()
                # Join? Might block. Best to fire and forget or short join.
                # sess["thread"].join(timeout=1) 
                # Remove from dict?
                del self.sessions[serial]
                return True
        return False
        
    def stop_all(self):
        with self.lock:
            for s in list(self.sessions.keys()):
                self.sessions[s]["stop_event"].set()
            self.sessions.clear()

    def get_active_sessions(self):
        # Returns list of serials
        with self.lock:
            return list(self.sessions.keys())
            
    def is_running(self, serial: str):
        with self.lock:
            return serial in self.sessions
