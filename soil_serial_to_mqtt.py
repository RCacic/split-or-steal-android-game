#!/usr/bin/env python3
import time
import json
import serial
import paho.mqtt.client as mqtt

SERIAL_PORT = "/dev/ttyACM0"
BAUD = 9600

TB_HOST = "mqtt.thingsboard.cloud"
TB_PORT = 1883
ACCESS_TOKEN = "4fknue2gat9jfkra6v6t"

TELEMETRY_TOPIC = "v1/devices/me/telemetry"
RPC_SUBSCRIBE_TOPIC = "v1/devices/me/rpc/request/+"


DRY_ON_LEVEL  = 4  
WET_OFF_LEVEL = 1 

AUTO_ENABLED = True


def parse_line(line: str):
    """
    Expected from Arduino:
      SOIL:<level>,RAW:<raw>
    Example:
      SOIL:5,RAW:570
    """
    line = line.strip()
    if not line.startswith("SOIL:"):
        return None

    try:
        parts = line.split(",")
        level = int(parts[0].split(":")[1])
        raw   = int(parts[1].split(":")[1])
        return level, raw
    except:
        return None

def main():
    global AUTO_ENABLED

    print(f"Opening serial: {SERIAL_PORT} @ {BAUD}")
    ser = serial.Serial(SERIAL_PORT, BAUD, timeout=1)
    time.sleep(2)

    print(f"Connecting ThingsBoard MQTT: {TB_HOST}:{TB_PORT}")
    client = mqtt.Client()
    client.username_pw_set(ACCESS_TOKEN)
    client.connect(TB_HOST, TB_PORT, keepalive=60)

    hose_state = "OFF"

    def on_message(client, userdata, msg):
        nonlocal hose_state
        global AUTO_ENABLED

        try:
            payload = json.loads(msg.payload.decode(errors="ignore"))
            method = payload.get("method")
            params = payload.get("params")

            print("RPC IN:", payload)

            if method == "hose_on":
                ser.write(b"HOSE_ON\n")
                hose_state = "ON"
                AUTO_ENABLED = False
                print("RPC -> HOSE_ON sent to Arduino")

            elif method == "hose_off":
                ser.write(b"HOSE_OFF\n")
                hose_state = "OFF"
                AUTO_ENABLED = False
                print("RPC -> HOSE_OFF sent to Arduino")

            elif method == "set_auto":
                AUTO_ENABLED = bool(params)
                print("RPC -> set_auto =", AUTO_ENABLED)

            else:
                print("RPC -> unknown method:", method)

        except Exception as e:
            print("RPC error:", e)

    client.subscribe(RPC_SUBSCRIBE_TOPIC)
    client.on_message = on_message
    client.loop_start()

    print("Connected. Reading serial + sending telemetry...")

    try:
        while True:
            line = ser.readline().decode(errors="ignore").strip()
            if not line:
                continue

       
            if line.startswith("ACK:") or line == "READY":
                print("SERIAL:", line)
                continue

            parsed = parse_line(line)
            if not parsed:
            
                continue

            level, raw = parsed

         
            if AUTO_ENABLED:
                if hose_state == "OFF" and level >= DRY_ON_LEVEL:
                    hose_state = "ON"
                    ser.write(b"HOSE_ON\n")
                    print("AUTO -> HOSE_ON")

                elif hose_state == "ON" and level <= WET_OFF_LEVEL:
                    hose_state = "OFF"
                    ser.write(b"HOSE_OFF\n")
                    print("AUTO -> HOSE_OFF")

            telemetry = {
                "soil_level": level,
                "soil_raw": raw,
                "hose_state": hose_state,
                "auto_enabled": AUTO_ENABLED
            }

            client.publish(TELEMETRY_TOPIC, json.dumps(telemetry))
            print("TB ->", telemetry)

            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\nStopping...")

    finally:
        client.loop_stop()
        client.disconnect()
        ser.close()

if __name__ == "__main__":
    main()
