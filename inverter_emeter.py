#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import os
import struct
import logging
import time
import json
import requests
from datetime import datetime
from emeter2 import emeterPacket
from sma_speedwire import SMA_SPEEDWIRE, smaError
from speedwiredecoder import decode_speedwire

# SMA inverters (IP-address, installer password, max_watt_limit)
inverters = [
    ("192.168.1.62", "my-sma-password", 15000),
    ("192.168.1.63", "my-sma-passwordmy-sma-password", 15000),
    ("192.168.1.64", "my-sma-password", 15000)
]

# Hoymiles inverters: (API-URL, max_watt_limit, max_consecutive_timeouts)
hoymiles_devices = [
#    ("http://192.168.1.72/api/livedata/status", 2500, 3)
]

# SMA Energy Meters
SUPPLY_METERS = []
CONSUME_METERS = [1900123456]
consume_to_supply = {
    'pconsume': 'psupply', 'pconsumecounter': 'psupplycounter'
}
meter_data = {}

ENERGY_STATE_FILE = "/tmp/sma_last_energy.json"

VIRTUAL_METER_SN = 1900888888 # should start with 1900 and have 10 digits in total
MULTICAST_GRP = '239.12.255.254'
MULTICAST_PORT = 9522

logging.basicConfig(
    filename='/var/log/sma_inverter_emeter.log',  # Log-Dateipfad
    filemode='a',
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Buffer for last valid values per Hoymiles device
hoymiles_state = {
    url: {
        "last_power": 0.0,
        "last_energy": 0.0,
        "timeouts": 0
    } for url, _, _ in hoymiles_devices
}

# Buffer for last valid values per SMA Energy Meter
energy_state = {}

# Load last known energy values per inverter (by IP or ID)
def load_energy_state():
    try:
        if os.path.exists(ENERGY_STATE_FILE):
            with open(ENERGY_STATE_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load energy state: {e}")
    return {}

# Save energy state to disk
def save_energy_state(state):
    try:
        os.makedirs(os.path.dirname(ENERGY_STATE_FILE), exist_ok=True)
        with open(ENERGY_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logging.error(f"Failed to save energy state: {e}")

# --- Helper to merge SMA Energy Meter values ---
def merge_to_same_keys(base, add, keys):
    for k in keys:
        if k in add:
            base[k] = base.get(k, 0.0) + add.get(k, 0.0)

def merge_consume_as_supply(base, add, mapping):
    for src, dst in mapping.items():
        if src in add:
            base[dst] = base.get(dst, 0.0) + add[src]

# Setup SMA Energy Meter listener
recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
recv_sock.bind(('', 9522))
mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_GRP), socket.INADDR_ANY)
recv_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

# Redirect errors and output to log file
class MyLogger:
    def write(self, message):
        if message != '\n':
            logging.info(message.strip())
    def flush(self):
        pass

# Init inverter objects
sma_devices = []
for ip, pwd, max_watt in inverters:
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
#    packet.addCounterValue(emeterPacket.SMA_NEGATIVE_ACTIVE_ENERGY, 0)
    
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

# Load previous energy state
energy_state = load_energy_state()

# Main loop
while True:
    try:
        total_power = 0.0
        total_energy = 0.0
        log_parts = []

        # 1. Collect SMA inverter data
        for (ip, pwd, max_watt), dev in zip(inverters, sma_devices):
            try:
                dev.update()
                p = float(dev.sensors["power_ac_total"]["value"] or 0.0)
                e = float(dev.sensors["energy_total"]["value"] or 0.0)

                if 0 < p <= max_watt:
                    total_power += p
                else:
                    logging.warning(f"[SMA] {ip}: Ignoring power value {p} W (limit {max_watt})")

                prev = energy_state.get(ip, 0.0)
                if e >= prev:
                    total_energy += e
                    energy_state[ip] = e
                else:
                    logging.warning(f"[SMA] Energy value for {ip} decreased from {prev} to {e}, ignoring")

                log_parts.append(f"SMA:{ip} P={round(p, 2)}W E={round(e, 3)}kWh")
            except smaError as e:
                logging.error(f"[SMA Update] Error at {ip}: {e}")

        # 2. Collect Hoymiles data
        for url, max_watt, max_timeouts in hoymiles_devices:
            try:
                response = requests.get(url, timeout=2)
                data = response.json()
                p_val = data.get("total", {}).get("Power", {}).get("v")
                p_unit = data.get("total", {}).get("Power", {}).get("u")
                e_val = data.get("total", {}).get("YieldTotal", {}).get("v")
                e_unit = data.get("total", {}).get("YieldTotal", {}).get("u")

                p = normalize_power(p_val, p_unit) if isinstance(p_val, (int, float)) else None
                e = normalize_energy(e_val, e_unit) if isinstance(e_val, (int, float)) else None

                if p is not None and 0 < p <= max_watt:
                    hoymiles_state[url]["last_power"] = p
                    hoymiles_state[url]["timeouts"] = 0
                    total_power += p
                else:
                    logging.warning(f"[Hoymiles] {url}: Ignoring power value {p} W (limit {max_watt})")

                prev = energy_state.get(url, 0.0)
                if e is not None and e >= prev:
                    total_energy += e
                    energy_state[url] = e
                    hoymiles_state[url]["last_energy"] = e
                else:
                    logging.warning(f"[Hoymiles] Energy value for {url} decreased from {prev} to {e}, using {prev}")
                    total_energy += prev

                log_parts.append(f"Hoymiles:{url.split('/')[2]} P={round(p or 0, 2)}W E={round(e or prev, 3)}kWh")

            except Exception as e:
                hoymiles_state[url]["timeouts"] += 1
                logging.error(f"[Hoymiles] Timeout/Error at {url}: {e} (#{hoymiles_state[url]['timeouts']})")

                if hoymiles_state[url]["timeouts"] <= max_timeouts:
                    total_power += hoymiles_state[url]["last_power"]
                    total_energy += hoymiles_state[url]["last_energy"]
                    log_parts.append(f"Hoymiles:{url.split('/')[2]} (cached) P={round(hoymiles_state[url]['last_power'], 2)}W E={round(hoymiles_state[url]['last_energy'], 3)}kWh")

        # 3. Decode SMA Energy Meter packets
        recv_sock.settimeout(0.5)
        for _ in range(10):  # Take max 10 packets
            try:
                data, _ = recv_sock.recvfrom(2048)
                decoded = decode_speedwire(data)
                if not decoded or "serial" not in decoded:
                    continue

                sn = str(decoded["serial"])
                if sn not in map(str, SUPPLY_METERS + CONSUME_METERS):
                    continue

                meter_data[sn] = decoded
                logging.debug(f"Received EM data from {sn}: {decoded}")
            except socket.timeout:
                break
            except Exception as e:
                logging.error(f"[EnergyMeter] Error while reading socket: {e}")
                break

        # 4. Summarize SMA Energy Meter values
        em_psupply = 0.0
        em_psupplycounter = 0.0

        for sn in map(str, CONSUME_METERS):
            if sn in meter_data:
                merge_consume_as_supply(meter_data[sn], meter_data[sn], consume_to_supply)

        for sn in map(str, SUPPLY_METERS + CONSUME_METERS):
            data = meter_data.get(sn)
            if not data:
                continue
            p = data.get("psupply", 0.0)
            e = data.get("psupplycounter", 0.0)
            em_psupply += p
            em_psupplycounter += e
            log_parts.append(f"SMAMeter:{sn} P={round(p, 2)}W E={round(e, 3)}kWh")
            energy_state[sn] = e  # Save latest meter value

        total_power += em_psupply
        total_energy += em_psupplycounter

        # Save updated energy state
        save_energy_state(energy_state)

        # Prepare and send result
        result = {
            "psupply": round(total_power, 2),
            "psupplyunit": "W",
            "psupplycounter": round(total_energy, 3),
            "psupplycounterunit": "kWh",
        }

        try:
            parse_and_emulate(result, send_sock)
        except Exception as e:
            logging.error(f"[Emulation] Error while sending emulated data: {e}")

        log_parts.append(f"SUM: P={result['psupply']}W E={result['psupplycounter']}kWh")
        logging.info(" | ".join(log_parts))

        time.sleep(5 if result['psupply'] > 0 else 60)

    except Exception as e:
        logging.critical(f"[MAIN LOOP] Uncaught exception: {e}", exc_info=True)
        time.sleep(10)
