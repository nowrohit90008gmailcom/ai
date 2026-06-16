"""
modules/comfyui_watchdog.py — Monitors ComfyUI health and restarts if hung.
"""

import time
import subprocess
import requests
from modules.logger import get_logger

log = get_logger("comfy_watchdog")

def monitor_comfyui(url="http://127.0.0.1:8188", timeout=10, max_fails=3):
    fails = 0
    log.info(f"Started ComfyUI Watchdog monitoring {url}")
    
    while True:
        try:
            r = requests.get(f"{url}/system_stats", timeout=timeout)
            if r.status_code == 200:
                fails = 0
            else:
                fails += 1
                log.warning(f"ComfyUI returned {r.status_code}. Fail count: {fails}")
        except Exception as e:
            fails += 1
            log.warning(f"ComfyUI check failed: {e}. Fail count: {fails}")
            
        if fails >= max_fails:
            log.error("ComfyUI is dead or hung! Restarting service...")
            try:
                # Assuming ComfyUI is managed by systemd
                subprocess.run(["sudo", "systemctl", "restart", "comfyui"], check=True)
                log.info("Restart command issued successfully.")
                
                # Wait for it to come back up before monitoring again
                time.sleep(30)
                fails = 0
            except Exception as e:
                log.error(f"Failed to restart ComfyUI: {e}")
                
        time.sleep(15)

if __name__ == "__main__":
    monitor_comfyui()
