#!/usr/bin/python3
import subprocess
import json
import os
import time

# --- CONFIGURATION ---
AMDGPU_TOP_CMD = ["amdgpu_top", "--json"]

def clear_screen():
    """Clears the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_dashboard(data):
    """Prints a formatted text dashboard of the JSON data."""
    clear_screen()
    print("=" * 60)
    print(f" AMDGPU Console Monitor | Time: {time.strftime('%Y-%m-%d %H:%M:%S')} ")
    print("=" * 60)

    devices = data.get("devices", [])
    if not devices:
        print("No GPU devices detected.")
        return

    for dev in devices:
        info = dev.get("Info", {})
        asic_name = info.get("ASIC Name", "Unknown ASIC")
        pci = info.get("PCI", "N/A")
        
        print(f"\nDEVICE: {asic_name}")
        print(f"PCI:    {pci}")
        print("-" * 30)

        # GPU Activity (GFX, MediaEngine, etc.)
        activity = dev.get("gpu_activity", {})
        if activity:
            print("GPU ACTIVITY:")
            for key, val_dict in activity.items():
                val = val_dict.get("value")
                unit = val_dict.get("unit", "")
                # Only display if value is non-zero and not MediaEngine
                if val is not None and (val != 0 or key == "GFX") and key != "MediaEngine":
                    print(f"  {key:<15}: {val}{unit}")
        else:
            print("GPU ACTIVITY: No data available")

        # Sensors (Temperature & Clocks)
        sensors = dev.get("Sensors", {})
        if sensors:
            print("\nSENSORS:")
            temp_edge = sensors.get("Edge Temperature", {}).get("value")
            if temp_edge is not None: print(f"  Temp (Edge)     : {temp_edge}°C")
            
            sclk = sensors.get("GFX_SCLK", {}).get("value")
            mclk = sensors.get("GFX_MCLK", {}).get("value")
            if sclk is not None: print(f"  GPU Clock (SCLK): {sclk} MHz")
            if mclk is not None: print(f"  Mem Clock (MCLK): {mclk} MHz")

            cpu_tctl = sensors.get("CPU Tctl", {}).get("value")
            if cpu_tctl is not None: print(f"  CPU Temp        : {cpu_tctl}°C")
            
            pwr = sensors.get("Average Power", {}).get("value")
            if pwr is not None: print(f"  Avg Power       : {pwr} W")

        # VRAM Usage (Using GTT as requested)
        vram = dev.get("VRAM", {})
        if vram:
            total_gtt = vram.get("Total GTT", {}).get("value", 0)
            used_gtt = vram.get("Total GTT Usage", {}).get("value", 0)
            if total_gtt > 0:
                # The values in JSON are already in MiB, not bytes.
                # Let's check the sample again: "Total GTT": {"unit":"MiB","value":16384}
                # My previous code was dividing by 1024 twice (once for MB and once more).
                percent = (used_gtt / total_gtt) * 100
                print(f"\nVRAM USAGE (GTT):")
                print(f"  {used_gtt:>7.2f} MiB / {total_gtt:>7.2f} MiB ({percent:.1f}%)")
        else:
            print("\nVRAM: No data available")

    print("\n" + "=" * 60)
    print(" Press Ctrl+C to exit ")
    print("=" * 60)

def main():
    # Start the process
    process = subprocess.Popen(AMDGPU_TOP_CMD, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    try:
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            
            try:
                data = json.loads(line)
                print_dashboard(data)
            except json.JSONDecodeError:
                continue 

    except KeyboardInterrupt:
        print("\nExiting...")
        process.terminate()
    except Exception as e:
        print(f"Error: {e}")
        process.terminate()

if __name__ == "__main__":
    main()
