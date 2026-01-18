import logging
import os
import time
import re
from core.adb import ADB

logger = logging.getLogger("ag-frida.core.root")

class RootAutomator:
    """
    Advanced Root Assistant.
    Supports Emulators, Real Devices (Pixel/Samsung), A/B Partitions.
    Android 9 - 14+
    """
    
    MAGISK_APK_URL = "https://github.com/topjohnwu/Magisk/releases/download/v27.0/Magisk-v27.0.apk"
    
    def __init__(self, serial: str):
        self.serial = serial
        self.adb = ADB(serial)
        self.work_dir = os.path.join(os.getcwd(), "root_artifacts")
        if not os.path.exists(self.work_dir):
            os.makedirs(self.work_dir)

    # ====================================
    # Core Device Intelligence
    # ====================================
    
    def get_device_info(self) -> dict:
        """Returns comprehensive device information for smart decisions."""
        try:
            info = {
                "model": self.adb.shell("getprop ro.product.model", check=False).strip(),
                "android_version": self.adb.shell("getprop ro.build.version.release", check=False).strip(),
                "sdk_level": self.adb.shell("getprop ro.build.version.sdk", check=False).strip(),
                "slot_suffix": self.adb.shell("getprop ro.boot.slot_suffix", check=False).strip(),
                "is_emulator": self._detect_emulator(),
                "root_access": self._check_root_type()
            }
            return info
        except:
            return {"error": "Failed to get device info"}
    
    def _detect_emulator(self) -> bool:
        """Comprehensive emulator detection using multiple indicators."""
        checks = [
            ("ro.kernel.qemu", "1"),           # QEMU-based (most emulators)
            ("ro.hardware", "goldfish"),       # Android Emulator
            ("ro.hardware", "ranchu"),         # Android Emulator (newer)
            ("ro.product.brand", "generic"),   # Generic brand
            ("ro.product.device", "generic"),  # Generic device
            ("ro.product.device", "sdk"),      # SDK builds
            ("ro.build.characteristics", "emulator"),
            ("ro.hardware.audio.primary", "goldfish"),
        ]
        
        for prop, indicator in checks:
            val = self.adb.shell(f"getprop {prop}", check=False).lower().strip()
            if indicator in val:
                return True
        
        # Also check if serial looks like emulator
        if self.serial and ("emulator" in self.serial.lower() or self.serial.startswith("127.0.0.1:")):
            return True
            
        return False
    
    def _check_root_type(self) -> str:
        """Determines root access type: 'adb_root', 'su', or 'none'."""
        # 1. Try adb root (works on debug builds/emulators)
        self.adb.root()
        time.sleep(0.5)
        id_out = self.adb.shell("id", check=False)
        if "uid=0(root)" in id_out:
            return "adb_root"
        
        # 2. Try su
        su_out = self.adb.shell("su -c id", check=False)
        if "uid=0(root)" in su_out:
            return "su"
            
        return "none"
    
    def find_boot_partition(self) -> dict:
        """
        Dynamically finds the correct boot partition.
        Returns dict with 'path', 'size', 'slot'.
        """
        slot = self.adb.shell("getprop ro.boot.slot_suffix", check=False).strip()
        is_ab = bool(slot)
        
        # Common paths to search (in order of priority)
        search_patterns = [
            f"/dev/block/by-name/boot{slot}",
            "/dev/block/by-name/boot",
            f"/dev/block/bootdevice/by-name/boot{slot}",
            "/dev/block/bootdevice/by-name/boot",
            "/dev/block/platform/*/by-name/boot*",
        ]
        
        # For Android 13+ (GKI), init_boot might be needed
        sdk = self.adb.shell("getprop ro.build.version.sdk", check=False).strip()
        if sdk.isdigit() and int(sdk) >= 33:
            search_patterns.insert(0, f"/dev/block/by-name/init_boot{slot}")
            search_patterns.insert(1, "/dev/block/by-name/init_boot")
        
        found_path = None
        
        # Search each pattern
        for pattern in search_patterns:
            # Expand wildcards using find
            if "*" in pattern:
                cmd = f"find /dev/block -name 'boot*' -o -name 'init_boot*' 2>/dev/null | head -n 5"
                out = self.adb.shell(cmd, check=False)
                if out:
                    for line in out.strip().split('\n'):
                        if line and self._verify_partition(line):
                            found_path = line.strip()
                            break
            else:
                if self._verify_partition(pattern):
                    found_path = pattern
                    break
        
        if not found_path:
            return {"status": "error", "message": "Boot partition not found. Device may not be supported."}
        
        # Get Size
        size_str = "Unknown"
        try:
            # ls -l gives size, or use blockdev
            size_out = self.adb.shell(f"ls -l {found_path} 2>/dev/null || echo 'symlink'", check=False)
            if "symlink" in size_out or "->" in size_out:
                # Resolve symlink, get actual block size
                resolve = self.adb.shell(f"readlink -f {found_path}", check=False).strip()
                size_bytes_out = self.adb.shell(f"cat /sys/class/block/$(basename {resolve})/size 2>/dev/null", check=False)
                if size_bytes_out.strip().isdigit():
                    size_bytes = int(size_bytes_out.strip()) * 512 # Sectors to bytes
                    size_str = f"{size_bytes // (1024*1024)} MB"
        except:
            pass

        return {
            "status": "ok",
            "path": found_path,
            "size": size_str,
            "slot": slot if slot else "N/A (Legacy)"
        }
    
    def _verify_partition(self, path: str) -> bool:
        """Verifies if a partition path exists and is readable."""
        out = self.adb.shell(f"ls -l {path}", check=False)
        return "No such file" not in out and path.split('/')[-1] in out

    # ====================================
    # Core Operations
    # ====================================

    def dump_boot(self) -> dict:
        """Dumps boot.img from device to PC. Smart slot handling."""
        try:
            root_type = self._check_root_type()
            if root_type == "none":
                return {"status": "error", "message": "❌ No Root Access. Requires 'adb root' (Emulator) or 'su' (Rooted Device)."}

            part_info = self.find_boot_partition()
            if part_info.get("status") == "error":
                return part_info
            
            boot_path = part_info["path"]
            slot = part_info.get("slot", "")
            
            timestamp = int(time.time())
            img_name = f"boot{slot}_{timestamp}.img"
            remote_dump = f"/sdcard/Download/{img_name}"
            local_dump = os.path.join(self.work_dir, img_name)

            logger.info(f"Dumping {boot_path} -> {remote_dump}")

            # Build command
            dd_cmd = f"dd if={boot_path} of={remote_dump}"
            if root_type == "su":
                dd_cmd = f"su -c '{dd_cmd}'"

            # Execute
            dump_result = self.adb.shell(dd_cmd, check=False)
            
            # Verify
            check_remote = self.adb.shell(f"ls -l {remote_dump}", check=False)
            if "No such file" in check_remote:
                return {"status": "error", "message": f"Dump command failed. Output: {dump_result}"}

            # Pull to PC
            logger.info(f"Pulling to {local_dump}")
            self.adb.pull(remote_dump, local_dump)

            if not os.path.exists(local_dump):
                return {"status": "error", "message": "Pull failed. File not created on PC."}
                
            file_size = os.path.getsize(local_dump) // (1024*1024)

            return {
                "status": "ok",
                "filename": img_name,
                "path": local_dump,
                "remote_path": remote_dump,
                "partition": boot_path,
                "size_mb": file_size,
                "slot": slot if slot else "N/A",
                "message": f"✅ Dumped to {img_name} ({file_size} MB). Ready for Magisk patching!"
            }

        except Exception as e:
            logger.error(f"Dump BOOT Failed: {e}")
            return {"status": "error", "message": f"Exception: {str(e)}"}


    def flash_boot(self, patched_image_filename: str) -> dict:
        """Flashes a patched boot image back to the device. Smart slot handling."""
        try:
            root_type = self._check_root_type()
            if root_type == "none":
                 return {"status": "error", "message": "❌ No Root Access."}

            local_path = os.path.join(self.work_dir, patched_image_filename)
            if not os.path.exists(local_path):
                 return {"status": "error", "message": f"File '{patched_image_filename}' not found in root_artifacts/"}

            part_info = self.find_boot_partition()
            if part_info.get("status") == "error":
                return part_info

            boot_path = part_info["path"]
            remote_path = f"/sdcard/Download/{patched_image_filename}"

            # Push
            logger.info(f"Pushing {local_path} -> {remote_path}")
            self.adb.push(local_path, remote_path)

            # Flash
            logger.info(f"Flashing {remote_path} -> {boot_path}")
            dd_cmd = f"dd if={remote_path} of={boot_path}"
            if root_type == "su":
                dd_cmd = f"su -c '{dd_cmd}'"
            
            flash_result = self.adb.shell(dd_cmd, check=False)
            
            # Cleanup
            self.adb.shell(f"rm {remote_path}", check=False)

            return {
                "status": "ok",
                "message": f"✅ Flashed '{patched_image_filename}' to {boot_path}. REBOOT to apply!",
                "output": flash_result
            }

        except Exception as e:
            logger.error(f"Flash BOOT Failed: {e}")
            return {"status": "error", "message": f"Exception: {str(e)}"}

    def install_magisk_app(self) -> dict:
        """Downloads and installs Magisk Manager APK."""
        try:
            import requests
            
            apk_name = "Magisk-v27.0.apk"
            local_apk = os.path.join(self.work_dir, apk_name)
            
            # Download if not cached
            if not os.path.exists(local_apk):
                logger.info(f"Downloading Magisk APK...")
                with requests.get(self.MAGISK_APK_URL, stream=True) as r:
                    r.raise_for_status()
                    with open(local_apk, 'wb') as f:
                        for chunk in r.iter_content(8192):
                            f.write(chunk)
            
            # Install
            logger.info(f"Installing {apk_name}...")
            self.adb.install(local_apk)
            
            return {"status": "ok", "message": "✅ Magisk App Installed!"}
        except Exception as e:
            return {"status": "error", "message": f"Install failed: {e}"}

    def launch_magisk_app(self) -> dict:
        """Attempts to open the Magisk app on the device."""
        try:
            # com.topjohnwu.magisk/.ui.MainActivity
            self.adb.shell("am start -n com.topjohnwu.magisk/.ui.MainActivity", check=False)
            return {"status": "ok", "message": "Launched Magisk App on device."}
        except Exception as e:
            return {"status": "error", "message": str(e)}
