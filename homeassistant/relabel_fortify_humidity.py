#!/usr/bin/env python3
"""Idempotently label the two humidity sensors on every Fortify Soil-Moisture device.

ZHA auto-discovers both the air (endpoint 1) and soil (endpoint 2) humidity sensors
with the default name "Humidity". This cannot be done cleanly in the zigpy quirk
(a quirk-defined sensor gets a different unique_id and would DUPLICATE the entity
instead of renaming it), so we set the entity-registry name over the websocket API.

Run this once after pairing a new Fortify Soil-Moisture sensor:

    HA_URL=ws://<ha-ip>:8123/api/websocket HA_TOKEN=<long-lived-token> \
        python3 relabel_fortify_humidity.py

Re-running is safe: already-labeled entities are skipped.
"""
import asyncio
import json
import os
import sys

import websockets

URL = os.environ.get("HA_URL", "ws://homeassistant.local:8123/api/websocket")
TOKEN = os.environ.get("HA_TOKEN") or sys.exit("set HA_TOKEN")

# unique_id endpoint -> desired entity-registry name
EP_LABEL = {"1-1029": "Air Humidity", "2-1029": "Soil Moisture"}


async def call(ws, i, payload):
    await ws.send(json.dumps({"id": i, **payload}))
    while True:
        m = json.loads(await ws.recv())
        if m.get("id") == i:
            return m


async def main():
    async with websockets.connect(URL, max_size=None) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": TOKEN}))
        if json.loads(await ws.recv()).get("type") != "auth_ok":
            sys.exit("auth failed")

        devs = (await call(ws, 1, {"type": "config/device_registry/list"}))["result"]
        ents = (await call(ws, 2, {"type": "config/entity_registry/list"}))["result"]
        fort = {
            d["id"]
            for d in devs
            if d.get("manufacturer") == "Fortify" and d.get("model") == "Soil-Moisture"
        }

        i = 10
        changed = 0
        for e in ents:
            if e.get("device_id") not in fort:
                continue
            uid = e.get("unique_id", "")
            for suffix, label in EP_LABEL.items():
                if uid.endswith(f"-{suffix}"):
                    if e.get("name") == label:
                        print(f"ok   {e['entity_id']} already '{label}'")
                    else:
                        i += 1
                        r = await call(
                            ws,
                            i,
                            {
                                "type": "config/entity_registry/update",
                                "entity_id": e["entity_id"],
                                "name": label,
                            },
                        )
                        if r.get("success"):
                            print(f"SET  {e['entity_id']} -> '{label}'")
                            changed += 1
                        else:
                            print(f"ERR  {e['entity_id']}: {r.get('error')}")
        print(f"done; {changed} change(s)")


asyncio.run(main())
