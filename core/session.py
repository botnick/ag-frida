import frida
import logging
import sys
import threading
import time
from typing import List, Optional
from rich.console import Console
from .server import ServerManager
from .adb import ADB

logger = logging.getLogger("ag-frida.core.session")
console = Console()

class SessionManager:
    """
    Handles Frida Attach/Spawn and Script Injection.
    Follows Industry Standard Lifecycle: Pre-Check -> Acquire -> Instrument -> Monitor.
    V3.0: Modularized & Robust.
    """
    def __init__(self, device_serial: str, remote_addr: str = None):
        self.serial = device_serial
        self.remote_addr = remote_addr # e.g. "127.0.0.1:35000"
        self.device = None 
        self.session = None
        self.scripts = []
        self.stop_event = threading.Event()
        self.pid = None
        
        # Circuit Breaker State
        self.crash_times = []
        self.CB_THRESHOLD = 3
        self.CB_WINDOW = 15 # Seconds
        self.healed_once = False # One-shot recovery lock

    def _check_circuit_breaker(self) -> bool:
        """Returns True if safe to proceed, False if breached."""
        now = time.time()
        self.crash_times = [t for t in self.crash_times if now - t < self.CB_WINDOW]
        self.crash_times.append(now)
        return len(self.crash_times) <= self.CB_THRESHOLD

    def _ensure_environment(self):
        """Phase 0: Environment Check"""
        try:
            if self.remote_addr:
                # Stealth Mode
                dm = frida.get_device_manager()
                self.device = dm.add_remote_device(self.remote_addr)
                # Verify calling get_application or similar to ensure connectivity
                # But for stealth, just adding remote device might pass even if down.
                # So we might want a quick ping?
                # For now, let's trust the bridge set it up, or fail at next step.
            else:
                # Standard Mode
                self.device = frida.get_device(id=self.serial)
        except Exception as e:
            # Attempt Recovery for Standard Mode
            if not self.remote_addr:
                # STRICT MANAGER vs WORKER SEPARATION
                # We DO NOT auto-revive here anymore. User must ensure server is running.
                console.print(f"[bold red]Frida Server not found or not running.[/bold red]")
                console.print(f"[yellow]Please use 'ag-frida --server start' or the Web Manager to start the server.[/yellow]")
                raise RuntimeError("Frida Server is not running. Please start it first.")
            else:
                raise e


    def _perform_spawn(self, target: str):
        """Phase 1A: Target Acquisition (Standard Spawn)"""
        logger.info(f"Spawning package: {target}")
        
        # Ensure clean state
        try:
            self.device.kill(target)
            time.sleep(0.5)
        except:
             pass 

        try:
            # Native Frida Spawn (Works now that versions are aligned)
            # This ensures we hook Zygote/Early-Startup, which is required for Java to be detected reliably.
            self.pid = self.device.spawn(target)
            self.session = self.device.attach(self.pid)
            logger.info(f"Spawned & Attached to PID {self.pid}")
            
        except Exception as e:
            msg = str(e).lower()
            if "timed out" in msg or "closed" in msg or "transport" in msg or "terminated" in msg:
                logger.warning(f"Spawn failed ({e}). Switching to ADB Launch Fallback...")
                self._adb_launch_fallback(target)
            else:
                raise e

    def _adb_launch_fallback(self, target: str):
        """Fallback mechanism for Emulators where spawn times out."""
        adb = ADB(self.serial)
        cmd = f"monkey -p {target} -c android.intent.category.LAUNCHER 1"
        logger.info(f"Running ADB Launch: {cmd}")
        adb.shell(cmd)
        time.sleep(6) # Safe wait for slow emulators

        # Find PID manually
        found_pid = None
        procs = self.device.enumerate_processes()
        for p in procs:
            if p.name == target:
                found_pid = p.pid
                break
        
        if found_pid:
            logger.info(f"ADB Launch Successful. Attaching to PID {found_pid}...")
            self.session = self.device.attach(found_pid)
            self.pid = found_pid
        else:
            self._diagnose_crash(adb, target)
            raise RuntimeError(f"ADB Launch failed. Process {target} not found (See crash report).")

    def _diagnose_crash(self, adb, target):
        """God Tier: Auto-Diagnose Crash from Logcat."""
        logger.info("Analyzing Logcat for crashes...")
        try:
            log_cmd = f"logcat -d -t 200 -s AndroidRuntime:E ActivityManager:E {target}:E"
            log_out = adb.shell(log_cmd)
            if log_out:
                crash_lines = [line for line in log_out.splitlines() if target in line or "FATAL" in line or "Exception" in line]
                if crash_lines:
                    unique_crash = list(dict.fromkeys(crash_lines[-10:]))
                    crash_report = "\n".join(unique_crash)
                    console.print(f"[bold red]Possible App Crash Detected:\n{crash_report}[/bold red]")
                    logger.error(f"Crash Report:\n{crash_report}")
        except Exception as le:
            logger.warning(f"Logcat analysis failed: {le}")

    def _perform_attach(self, target: str):
        """Phase 1B: Target Acquisition (Attach) - Strict Mode with Smart Resolution"""
        logger.info(f"Attaching to process: {target}")
        try:
            # 1. Try Direct Attach (Process Name or PID)
            try:
                # Handle PID if integer
                if target.isdigit():
                    self.session = self.device.attach(int(target))
                else:
                    self.session = self.device.attach(target)
            except frida.ProcessNotFoundError:
                # 2. Smart Resolve: Package Name -> Running PID
                logger.info(f"Process '{target}' not found direct. Trying to resolve Package Name...")
                pid = self._resolve_pid_from_pkg(target)
                if pid:
                    logger.info(f"Resolved '{target}' to PID {pid}. Attaching...")
                    self.session = self.device.attach(pid)
                else:
                    raise # Re-raise if resolution failed
                    
        except frida.ProcessNotFoundError:
            # Strict mode: Fail immediately so loop can retry or user knows.
            # We explicitly removed 'Smart Search' per user request.
            logger.warning(f"Process '{target}' not found. Waiting...")
            time.sleep(1)
            raise 

    def _resolve_pid_from_pkg(self, target: str) -> Optional[int]:
        """Resolves Package Name (com.example) to PID utilizing both App and Process lists."""
        try:
            # 1. Match Package Name to App Name
            target_name = None
            apps = self.device.enumerate_applications()
            for app in apps:
                if app.identifier == target or app.name == target:
                    # If direct PID is valid, use it
                    if app.pid != 0:
                        return app.pid
                    target_name = app.name # e.g. "Mico"
                    break
            
            # 2. If we found a name but no PID, scan running processes for that Name
            if target_name:
                logger.info(f"App '{target_name}' found (PID=0). Scanning processes for name match...")
                procs = self.device.enumerate_processes()
                for p in procs:
                    if p.name == target_name:
                        return p.pid
                        
        except Exception as e:
            logger.error(f"Resolution failed: {e}")
            
        # 3. Last Resort: ADB PID Lookup (For "Blind" Emulators)
        try:
            logger.info(f"Resolution failed via Frida. Trying ADB fallback for '{target}'...")
            # We need a temporary ADB instance or use subprocess directly for speed/simplicity
            # Using subprocess to avoid circular dependency if any, but ADB class is safe.
            from .adb import ADB
            adb = ADB(self.serial)
            # 'pidof' is standard on Android, sometimes requires root or specific path but usually works.
            # Alternately 'pgrep' or parsing 'ps'. pidof is simplest.
            pid_str = adb.shell(f"pidof {target}") 
            if pid_str and pid_str.strip().isdigit():
                pid = int(pid_str.strip().split()[0]) # distinct PIDs, take first
                logger.info(f"ADB resolved '{target}' to PID {pid}")
                return pid
        except Exception as ae:
            logger.warning(f"ADB Resolution failed: {ae}")

        return None

    def _load_script(self, script_loader):
        """Phase 2: Instrumentation"""
        logger.info("Loading scripts (Dynamic)...")
        script_contents = script_loader()
        
        self.scripts = [] 
        if not script_contents:
            script_contents = ["console.log('[ag-frida] Connected (No script)!');"]

        for idx, content in enumerate(script_contents):
            logger.info(f"Injecting script #{idx+1}...")
            
            # Direct injection (Native Behavior)
            try:
                script = self.session.create_script(content)
                script.on('message', self._on_message)
                script.load()
                self.scripts.append(script)
            except Exception as e:
                console.print(f"[bold red]Failed to load script #{idx+1}: {e}[/bold red]")
                logger.error(f"Script Load Error: {e}")
                script.load()
                self.scripts.append(script)
            except Exception as e:
                console.print(f"[bold red]Failed to load script #{idx+1}: {e}[/bold red]")
                logger.error(f"Script Load Error: {e}")

    def _on_message(self, message, data):
        # ... (Existing) ...
        prefix = f"[{self.serial}]"
        if message['type'] == 'send':
            console.print(f"[green][SCRIPT]{prefix}[/green] {message['payload']}")
            logging.getLogger("ag-frida").info(f"[SCRIPT]{prefix} {message['payload']}")
        elif message['type'] == 'error':
            error_msg = message.get('stack', message)
            console.print(f"[bold red][ERROR]{prefix}[/bold red] {error_msg}")
            logging.getLogger("ag-frida").error(f"[SCRIPT ERROR]{prefix} {error_msg}")
        else:
            console.print(f"[dim]{message}[/dim]")

    def _monitor_session(self):
        # ... (Existing) ...
        console.print(f"[bold green]Frida Session Active.[/bold green]")
        while not self.stop_event.is_set():
            if self.session.is_detached:
                # ...
                pass
            self.stop_event.wait(0.5)

    def run(self, target: str, mode: str, script_loader: callable, auto_restart: bool = False):
        """Main Orchestrator"""
        self.stop_event.clear()
        
        while not self.stop_event.is_set():
            try:
                # 0. Check Env
                self._ensure_environment()

                # 1. Acquire
                if mode.lower() == 'spawn':
                    self._perform_spawn(target)
                else:
                    self._perform_attach(target)

                # 2. Instrument (Load Script BEFORE Resume)
                self._load_script(script_loader)

                # 3. Resume (if spawn)
                if mode.lower() == 'spawn' and self.pid:
                    logger.info("Resuming main thread...")
                    self.device.resume(self.pid)

                # 4. Monitor
                self._monitor_session()
                
                break

            except KeyboardInterrupt:
                # ...
                pass
            except Exception as e:
                # ...
                if not auto_restart:
                    console.print(f"[bold red]Error: {e}[/bold red]")
                    break
                self._handle_recovery(e)
            
            finally:
                self.cleanup()

    def _handle_recovery(self, e):
        """Phase 5: Recovery Logic"""
        if self.stop_event.is_set(): return

        console.print(f"[bold red]Error: {e}[/bold red]")
        logger.error(f"Session Error: {e}")

        # Check Circuit Breaker
        if not self._check_circuit_breaker():
            console.print("[bold red]CRITICAL: Boot Loop Detected. Stopping.[/bold red]")
            self.stop_event.set()
            return

        # Special Healing: System Server
        if "system_server" in str(e) and self.remote_addr:
             if self.healed_once:
                 console.print("[bold red]CRITICAL: Self-Healing failed. Reboot required.[/bold red]")
                 self.stop_event.set()
                 return
             
             logger.warning("Healing frida-server...")
             self.healed_once = True
             try:
                 port = int(self.remote_addr.split(":")[1])
                 sm = ServerManager(self.serial)
                 sm.kill_server()
                 sm.start_stealth_server(port)
                 time.sleep(3)
             except Exception as he:
                 logger.error(f"Healing failed: {he}")

        console.print("[bold yellow]Restarting session in 2 seconds...[/bold yellow]")
        time.sleep(2)

    def cleanup(self):
        for s in self.scripts:
            try: s.unload()
            except: pass
        if self.session:
            try: self.session.detach()
            except: pass
        self.session = None
