#!/bin/bash

# SmartPanda CAN Interface Setup Script
# Initializes the CAN interfaces with the correct bitrates.

# Exit immediately if a command exits with a non-zero status.
set -e

echo "🐼 SmartPanda - Initializing CAN Interfaces..."

# Setup C-CAN (High Speed - 500kbps)
# Connected to Engine, ABS, City Power Steering
echo "[*] Setting up can0 (C-CAN) at 500kbps..."
sudo ip link set can0 up type can bitrate 500000 listen-only on
echo "    [OK] can0 is UP"

# Setup B-CAN (Low Speed - 50kbps)
# Connected to Body Computer, Dashboard, Lights
echo "[*] Setting up can1 (B-CAN) at 50kbps..."
sudo ip link set can1 up type can bitrate 50000 listen-only on
echo "    [OK] can1 is UP"

echo "✅ Setup Complete. Use 'ifconfig' to verify."
