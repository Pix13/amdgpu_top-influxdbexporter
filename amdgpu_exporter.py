#!/usr/bin/python3
import subprocess
import json
import os
import requests
from datetime import datetime

# --- CONFIGURATION ---
# Load environment variables from ~/.env.influxdb
ENV_FILE = os.path.expanduser("~/.env.influxdb")

def load_env():
    config = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    key, value = line.split("=", 1)
                    config[key] = value
                except ValueError:
                    continue
    return config

env_config = load_env()

# Note: User should ensure amdgpu_top is in PATH or provide absolute path.
AMDGPU_TOP_CMD = ["amdgpu_top", "--json"]
INFLUXDB_URL = env_config.get("INFLUXDB_URL", "http://localhost:8086/api/v2/write") 
INFLUXDB_TOKEN = env_config.get("INFLUXDB_TOKEN")
INFLUXDB_ORG = env_config.get("INFLUXDB_ORG")
INFLUXDB_BUCKET = env_config.get("INFLUXDB_BUCKET")

def push_to_influx(line_protocol):
    """Sends data to InfluxDB using Line Protocol."""
    if not INFLUXDB_TOKEN or not INFLUXDB_ORG or not INFLUXDB_BUCKET:
        print("Error: Missing InfluxDB configuration in ~/.env.influxdb")
        return

    headers = {
        "Authorization": f"Token {INFLUXDB_TOKEN}",
        "Content-Type": "text/plain; charset=utf-8"
    }
    try:
        # Using precision=s or ms depending on how you want to handle timestamps
        response = requests.post(
            f"{INFLUXDB_URL}?org={INFLUXDB_ORG}&bucket={INFLUXDB_BUCKET}&precision=s", 
            data=line_protocol, 
            headers=headers
        )
        response.raise_for_status()
    except Exception as e:
        print(f"Error pushing to InfluxDB: {e}")

def parse_and_convert(json_data):
    """
    Converts amdgpu_top JSON structure into InfluxDB Line Protocol.
    Based on the documented output format.
    """
    lines = []
    # We'll let InfluxDB handle timestamping or add one if needed. 
    # For simplicity in this bridge, we use current time for each batch.
    
    devices = json_data.get("devices", [])
    for dev in devices:
        info = dev.get("Info", {})
        asic_name = info.get("ASIC Name", "unknown")
        device_name = info.get("DeviceName", "unknown").replace(" ", "_")
        pci_id = info.get("PCI", "unknown").replace(":", "_")
        
        # Use ASIC name for the tag to match console display preference, 
        # but we keep device_name as a secondary identifier if needed.
        tags = f"device_name={asic_name.replace(' ', '_')},pci={pci_id}"
        
        # 1. Parse GPU Activity (GFX, MediaEngine, etc.)
        activity = dev.get("gpu_activity", {})
        for key, data in activity.items():
            val = data.get("value")
            if val is not None:
                lines.append(f"gpu_activity,{tags} {key}={val}")

        # 2. Parse Sensors (Temperature & Clocks)
        sensors = dev.get("Sensors", {})
        if sensors:
            # Temperature - Edge/GFX
            temp_edge = sensors.get("Edge Temperature", {}).get("value")
            if temp_edge is not None:
                lines.append(f"temperature,{tags} edge={temp_edge}")
            
            # GPU Clocks (SCLK, MCLK)
            sclk = sensors.get("GFX_SCLK", {}).get("value")
            mclk = sensors.get("GFX_MCLK", {}).get("value")
            if sclk is not None: lines.append(f"clock,{tags} gfx_sclk={sclk}")
            if mclk is not None: lines.append(f"clock,{tags} gfx_mclk={mclk}")

            # Power (Average/GFX)
            pwr = sensors.get("Average Power", {}).get("value")
            if pwr is not None:
                lines.append(f"power,{tags} avg_power={pwr}")

        # 3. VRAM Usage (Using GTT as requested)
        vram_data = dev.get("VRAM", {})
        if vram_data:
            total_gtt = vram_data.get("Total GTT", {}).get("value", 0)
            used_gtt = vram_data.get("Total GTT Usage", {}).get("value", 0)
            if total_gtt > 0:
                lines.append(f"vram,{tags} used={used_gtt},total={total_gtt}")

        # 4. CPU Stats (from Sensors)
        cpu_tctl = sensors.get("CPU Tctl", {}).get("value")
        if cpu_tctl is not None:
            lines.append(f"cpu,{tags} tctl_temp={cpu_tctl}")

    return "\n".join(lines)

def main():
    print("Starting amdgpu_top bridge...")
    print(f"Targeting InfluxDB at: {INFLUXDB_URL}")
    
    # Start the process
    process = subprocess.Popen(AMDGPU_TOP_CMD, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    try:
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            
            try:
                # amdgpu_top --json outputs one JSON object per update interval
                data = json.loads(line)
                lp_data = parse_and_convert(data)
                if lp_data:
                    push_to_influx(lp_data)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Pushed metrics to InfluxDB")
            except json.JSONDecodeError as e:
                # This can happen if the output isn't a single complete JSON line
                continue 
            except Exception as e:
                print(f"Processing error: {e}")

    except KeyboardInterrupt:
        print("\nStopping bridge...")
        process.terminate()
    except Exception as e:
        print(f"Fatal error: {e}")
        process.terminate()

if __name__ == "__main__":
    main()