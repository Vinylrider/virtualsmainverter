#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import struct
import logging
import time
import json
import requests
from emeter2 import emeterPacket
from sma_speedwire import SMA_SPEEDWIRE, smaError

# SMA inverters (IP-address, installer password)
inverters = [
    ("192.168.1.62", "your-sma-password"),
    ("192.168.1.63", "your-sma-password!"),
    ("192.168.1.64", "your-sma-password!")
]

# Hoymiles inverters: List of API-URLs
hoymiles_urls = [
    "http://192.168.1.72/api/livedata/status"
]

VIRTUAL_METER_SN = 1900888888 # should start with 1900 and have 10 digits in total
MULTICAST_GRP = '239.12.255.254'
MULTICAST_PORT = 9522

logging.basicConfig(
    filename='/var/log/sma_virtual_emeter.log',  # Log-Dateipfad
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)

# Redirect errors and output to log file
class MyLogger:
    def write(self, message):
        if message != '\n':
            logging.info(message.strip())
    def flush(self):
        pass

# Init inverter objects
sma_devices = []
for ip, pwd in inverters:
    try:
        dev = SMA_SPEEDWIRE(ip, pwd)
        dev.init()
        sma_devices.append(dev)
    except smaError as e:
        print(f"Init-error at {ip}: {e}")

def normalize_power(value, unit):
    """Convert power to watts."""
    if unit == "W":
        return value
    elif unit == "kW":
        return value * 1000
    elif unit == "mW":
        return value / 1000
    else:
        raise ValueError(f"Unkown power unit: {unit}")

def normalize_energy(value, unit):
    """Convert energy to kWh."""
    if unit == "kWh":
        return value
    elif unit == "Wh":
        return value / 1000
    elif unit == "MWh":
        return value * 1000
    else:
        raise ValueError(f"Unknown energy unit: {unit}")

def setup_sender_socket():
    return socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

def parse_and_emulate(data_dict, send_sock):
    timestamp = int(time.time() * 1000)
    packet = emeterPacket(int(VIRTUAL_METER_SN))
    packet.begin(timestamp)

    # Total power/energy consumption (positive) (Summierte Leistung/Energie Bezug (positiv))
    packet.addMeasurementValue(emeterPacket.SMA_POSITIVE_ACTIVE_POWER, 0)
    packet.addCounterValue(emeterPacket.SMA_POSITIVE_ACTIVE_ENERGY, 0)
    
    # Total power/energy feed-in (negative) (Summierte Leistung/Energie Einspeisung (negativ))
    packet.addMeasurementValue(emeterPacket.SMA_NEGATIVE_ACTIVE_POWER, round(data_dict['psupply'] * 10))
    packet.addCounterValue(emeterPacket.SMA_NEGATIVE_ACTIVE_ENERGY, round(data_dict['psupplycounter'] * 1000 * 3600))
    
    # Reactive power (Blindleistung)
    packet.addMeasurementValue(emeterPacket.SMA_POSITIVE_REACTIVE_POWER, 0)
    packet.addCounterValue(emeterPacket.SMA_POSITIVE_REACTIVE_ENERGY, 0)
    packet.addMeasurementValue(emeterPacket.SMA_NEGATIVE_REACTIVE_POWER, 0)
    packet.addCounterValue(emeterPacket.SMA_NEGATIVE_REACTIVE_ENERGY, 0)

    # Apparent power (Scheinleistung)
    packet.addMeasurementValue(emeterPacket.SMA_POSITIVE_APPARENT_POWER, 0)
    packet.addCounterValue(emeterPacket.SMA_POSITIVE_APPARENT_ENERGY, 0)
    packet.addMeasurementValue(emeterPacket.SMA_NEGATIVE_APPARENT_POWER, 0)
    packet.addCounterValue(emeterPacket.SMA_NEGATIVE_APPARENT_ENERGY, 0)
                
    # cos(phi)
    packet.addMeasurementValue(emeterPacket.SMA_POWER_FACTOR, 0)

    # Phase 1
    packet.addMeasurementValue(emeterPacket.SMA_POSITIVE_ACTIVE_POWER_L1, 0)
    packet.addCounterValue(emeterPacket.SMA_POSITIVE_ACTIVE_ENERGY_L1, 0)
    packet.addMeasurementValue(emeterPacket.SMA_NEGATIVE_ACTIVE_POWER_L1, 0)
    packet.addCounterValue(emeterPacket.SMA_NEGATIVE_ACTIVE_ENERGY_L1, 0)
    packet.addMeasurementValue(emeterPacket.SMA_POSITIVE_REACTIVE_POWER_L1, 0)
    packet.addCounterValue(emeterPacket.SMA_POSITIVE_REACTIVE_ENERGY_L1, 0)
    packet.addMeasurementValue(emeterPacket.SMA_NEGATIVE_REACTIVE_POWER_L1, 0)
    packet.addCounterValue(emeterPacket.SMA_NEGATIVE_REACTIVE_ENERGY_L1, 0)
    packet.addMeasurementValue(emeterPacket.SMA_POSITIVE_APPARENT_POWER_L1, 0)
    packet.addCounterValue(emeterPacket.SMA_POSITIVE_APPARENT_ENERGY_L1, 0)
    packet.addMeasurementValue(emeterPacket.SMA_NEGATIVE_APPARENT_POWER_L1, 0)
    packet.addCounterValue(emeterPacket.SMA_NEGATIVE_APPARENT_ENERGY_L1, 0)
    packet.addMeasurementValue(emeterPacket.SMA_VOLTAGE_L1, 0)
    packet.addMeasurementValue(emeterPacket.SMA_CURRENT_L1, 0)
    packet.addMeasurementValue(emeterPacket.SMA_POWER_FACTOR_L1, 0)
            
    # Phase 2
    packet.addMeasurementValue(emeterPacket.SMA_POSITIVE_ACTIVE_POWER_L2, 0)
    packet.addCounterValue(emeterPacket.SMA_POSITIVE_ACTIVE_ENERGY_L2, 0)
    packet.addMeasurementValue(emeterPacket.SMA_NEGATIVE_ACTIVE_POWER_L2, 0)
    packet.addCounterValue(emeterPacket.SMA_NEGATIVE_ACTIVE_ENERGY_L2, 0)
    packet.addMeasurementValue(emeterPacket.SMA_POSITIVE_REACTIVE_POWER_L2, 0)
    packet.addCounterValue(emeterPacket.SMA_POSITIVE_REACTIVE_ENERGY_L2, 0)
    packet.addMeasurementValue(emeterPacket.SMA_NEGATIVE_REACTIVE_POWER_L2, 0)
    packet.addCounterValue(emeterPacket.SMA_NEGATIVE_REACTIVE_ENERGY_L2, 0)
    packet.addMeasurementValue(emeterPacket.SMA_POSITIVE_APPARENT_POWER_L2, 0)
    packet.addCounterValue(emeterPacket.SMA_POSITIVE_APPARENT_ENERGY_L2, 0)
    packet.addMeasurementValue(emeterPacket.SMA_NEGATIVE_APPARENT_POWER_L2, 0)
    packet.addCounterValue(emeterPacket.SMA_NEGATIVE_APPARENT_ENERGY_L2, 0)
    packet.addMeasurementValue(emeterPacket.SMA_VOLTAGE_L2, 0)
    packet.addMeasurementValue(emeterPacket.SMA_CURRENT_L2, 0)
    packet.addMeasurementValue(emeterPacket.SMA_POWER_FACTOR_L2, 0)
                    
    # Phase 3
    packet.addMeasurementValue(emeterPacket.SMA_POSITIVE_ACTIVE_POWER_L3, 0)
    packet.addCounterValue(emeterPacket.SMA_POSITIVE_ACTIVE_ENERGY_L3, 0)
    packet.addMeasurementValue(emeterPacket.SMA_NEGATIVE_ACTIVE_POWER_L3, 0)
    packet.addCounterValue(emeterPacket.SMA_NEGATIVE_ACTIVE_ENERGY_L3, 0)
    packet.addMeasurementValue(emeterPacket.SMA_POSITIVE_REACTIVE_POWER_L3, 0)
    packet.addCounterValue(emeterPacket.SMA_POSITIVE_REACTIVE_ENERGY_L3, 0)
    packet.addMeasurementValue(emeterPacket.SMA_NEGATIVE_REACTIVE_POWER_L3, 0)
    packet.addCounterValue(emeterPacket.SMA_NEGATIVE_REACTIVE_ENERGY_L3, 0)
    packet.addMeasurementValue(emeterPacket.SMA_POSITIVE_APPARENT_POWER_L3, 0)
    packet.addCounterValue(emeterPacket.SMA_POSITIVE_APPARENT_ENERGY_L3, 0)
    packet.addMeasurementValue(emeterPacket.SMA_NEGATIVE_APPARENT_POWER_L3, 0)
    packet.addCounterValue(emeterPacket.SMA_NEGATIVE_APPARENT_ENERGY_L3, 0)
    packet.addMeasurementValue(emeterPacket.SMA_VOLTAGE_L3, 0)
    packet.addMeasurementValue(emeterPacket.SMA_CURRENT_L3, 0)
    packet.addMeasurementValue(emeterPacket.SMA_POWER_FACTOR_L3, 0)

    packet.end()

    send_sock.sendto(packet.getData()[:packet.getLength()], (MULTICAST_GRP, MULTICAST_PORT))

# Endless looping getting values
send_sock = setup_sender_socket()
send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)

while True:
    total_power = 0.0
    total_energy = 0.0

    # --- Get SMA data ---
    for dev in sma_devices:
        try:
            dev.update()
            total_power += float(dev.sensors["power_ac_total"]["value"] or 0.0)
            total_energy += float(dev.sensors["energy_total"]["value"] or 0.0)
        except smaError as e:
            print(f"[SMA Update] Error at {dev.host}: {e}")

    # --- Get Hoymiles data ---
    for url in hoymiles_urls:
        try:
            response = requests.get(url, timeout=2)
            data = response.json()
            # Power
            p_val = data["total"]["Power"]["v"]
            p_unit = data["total"]["Power"]["u"]
            total_power += normalize_power(p_val, p_unit)
            # Energy
            e_val = data["total"]["YieldTotal"]["v"]
            e_unit = data["total"]["YieldTotal"]["u"]
            total_energy += normalize_energy(e_val, e_unit)
        except Exception as e:
            print(f"[Hoymiles] Error at {url}: {e}")

    # --- Result-JSON ---
    result = {
        "psupply": round(total_power, 2),
        "psupplyunit": "W",
        "psupplycounter": round(total_energy, 3),
        "psupplycounterunit": "kWh",
    }
    parse_and_emulate(result, send_sock)
    print(json.dumps(result, indent=2))
    time.sleep(3)
