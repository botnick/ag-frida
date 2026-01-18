"""
CLI Bridge for Frida
Calls frida CLI directly via subprocess to bypass Python API issues.
This guarantees the same behavior as the working 'frida -U -f' command.
"""

import subprocess
import threading
import tempfile
import os
import time
import logging
from typing import List, Optional, Callable
from rich.console import Console

logger = logging.getLogger("ag-frida.core.cli_bridge")
console = Console()


class CLIBridge:
    """
    Executes Frida via CLI subprocess.
    Bypasses Python API to match exact behavior of 'frida -U -f package -l script.js'.
    """
    
    def __init__(self, device_serial: str = None):
        self.serial = device_serial
        self.process: Optional[subprocess.Popen] = None
        self.stop_event = threading.Event()
        self._output_thread: Optional[threading.Thread] = None
        
    def _build_command(self, target: str, script_path: str, mode: str = "spawn") -> List[str]:
        """Build the frida CLI command."""
        cmd = ["frida"]
        
        # Device selection
        if self.serial:
            cmd.extend(["-D", self.serial])
        else:
            cmd.append("-U")  # USB device
        
        # Mode: spawn or attach logic
        # If target is PID (digits), we MUST use -p (attach)
        if target.isdigit():
            cmd.extend(["-p", target])
        elif mode == "spawn":
            cmd.extend(["-f", target])
        else:
            # Attach by name
            cmd.extend(["-n", target])
        
        # Script
        if script_path:
            cmd.extend(["-l", script_path])
        
        # Quiet mode (suppress banner for cleaner output)
        # cmd.append("-q")  # Uncomment if you want to suppress the banner
        
        return cmd
    
    def _stream_output(self, process: subprocess.Popen, on_message: Callable = None):
        """Stream stdout/stderr from the frida process."""
        try:
            for line in iter(process.stdout.readline, ''):
                if self.stop_event.is_set():
                    break
                if line:
                    line = line.strip()
                    if line:
                        # Parse and display output
                        if line.startswith("[") or line.startswith("Spawning") or line.startswith("Spawned"):
                            console.print(f"[green]{line}[/green]")
                        elif "error" in line.lower() or "Error" in line:
                            console.print(f"[bold red]{line}[/bold red]")
                            logger.error(line)
                        else:
                            console.print(f"[dim]{line}[/dim]")
                        
                        if on_message:
                            on_message({"type": "send", "payload": line}, None)
        except Exception as e:
            logger.warning(f"Output stream error: {e}")
    
    def run(self, target: str, mode: str, scripts: List[str], 
            auto_restart: bool = False, on_message: Callable = None):
        """
        Main execution method.
        
        Args:
            target: Package name or process name
            mode: 'spawn' or 'attach'
            scripts: List of script contents (will be combined)
            auto_restart: Whether to restart on crash
            on_message: Callback for script messages
        """
        self.stop_event.clear()
        
        # Combine all scripts into one temp file
        combined_script = "\n\n// --- Script Boundary ---\n\n".join(scripts) if scripts else ""
        
        temp_script_path = None
        if combined_script:
            # Write to temp file
            fd, temp_script_path = tempfile.mkstemp(suffix=".js", prefix="ag_frida_")
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(combined_script)
            logger.info(f"Combined script written to: {temp_script_path}")
        
        import signal
        
        # Signal Handler for Ctrl+C (Only if Main Thread)
        original_sigint = None
        if threading.current_thread() is threading.main_thread():
            original_sigint = signal.getsignal(signal.SIGINT)
            
            def handle_sigint(signum, frame):
                console.print("\n[yellow]Ctrl+C Detected. Stopping...[/yellow]")
                self.stop()
                
            signal.signal(signal.SIGINT, handle_sigint)
        
        try:
            while not self.stop_event.is_set():
                # Build command
                cmd = self._build_command(target, temp_script_path, mode)
                logger.info(f"Executing: {' '.join(cmd)}")
                console.print(f"[bold cyan]Running: {' '.join(cmd)}[/bold cyan]")
                
                # Start process
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    bufsize=1,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0 
                    # New Process Group allows us to send signal to the whole tree
                )
                
                console.print(f"[bold green]Frida Session Active (CLI Bridge).[/bold green]")
                console.print(f"[dim]Press Ctrl+C to stop.[/dim]")
                
                # Stream output in a thread
                self._output_thread = threading.Thread(
                    target=self._stream_output,
                    args=(self.process, on_message),
                    daemon=True
                )
                self._output_thread.start()
                
                # Wait for process to complete, checking for stops
                while self.process.poll() is None:
                     if self.stop_event.is_set():
                         self.stop()
                         break
                     time.sleep(0.5)
                
                if self.stop_event.is_set():
                    break
                
                return_code = self.process.poll()
                
                if return_code is not None and return_code != 0:
                    console.print(f"[bold red]Process exited with code {return_code}[/bold red]")
                    
                    if auto_restart and not self.stop_event.is_set():
                        console.print("[yellow]Restarting in 2 seconds...[/yellow]")
                        time.sleep(2)
                        continue
                    else:
                        break
                else:
                    # Normal exit
                    break
                    
        except KeyboardInterrupt:
            # Fallback if signal handler missed it (e.g. slight race)
            console.print("\n[yellow]Stopping...[/yellow]")
            self.stop()
        except Exception as e:
            logger.error(f"CLI Bridge error: {e}")
            console.print(f"[bold red]Error: {e}[/bold red]")
        finally:
            # Restore signal
            if original_sigint:
                signal.signal(signal.SIGINT, original_sigint)
            
            # Cleanup temp file
            if temp_script_path and os.path.exists(temp_script_path):
                try:
                    os.remove(temp_script_path)
                except:
                    pass
            self.cleanup()
    
    def stop(self):
        """Stop the running frida process."""
        self.stop_event.set()
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception as e:
                logger.warning(f"Error stopping process: {e}")
    
    def cleanup(self):
        """Cleanup resources."""
        self.stop()
        self.process = None


def test_cli_bridge():
    """Quick test of CLI bridge."""
    bridge = CLIBridge()
    
    test_script = """
console.log("[CLI Bridge Test] Starting...");
if (Java.available) {
    console.log("[+] Java is AVAILABLE!");
    console.log("[+] Android Version: " + Java.androidVersion);
} else {
    console.log("[-] Java not available");
}
"""
    
    console.print("[bold]Testing CLI Bridge with com.mico...[/bold]")
    bridge.run(
        target="com.mico",
        mode="spawn",
        scripts=[test_script],
        auto_restart=False
    )


if __name__ == "__main__":
    test_cli_bridge()
