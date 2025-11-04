import os, json, time, math
from datetime import datetime, timedelta, timezone
import requests
import numpy as np

AIO_USER = os.environ["AIO_USERNAME"]
AIO_KEY = os.environ["AIO_KEY"]

BASE = f"https://io.adafruit.com/api/v2/{AIO_USER}/feeds"
HEADERS = {"X-AIO-Key": AIO_KEY}

# Pull last N samples from feed as floats (ignore bad)
def fetch_feed(feed, limit=1000):
    url = f"{BASE}/{feed}/data"
    r = requests.get(url, params={"limit": limit}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    vals = []
    for d in data:
        v = d.get("value")
        try:
            vals.append(float(v))
        except:
            pass
    return list(reversed(vals))  # chronological

def quantile(arr, q):
    if not arr: return None
    return float(np.percentile(np.array(arr), q))

def build_rules(temp, hum, ldr):
    # Fallbacks if empty
    if not temp or not hum:
        # keep seed defaults
        return {
            "version": int(time.time()),
            "individual": [
                {"sensor": "temp", "op": ">=", "value": 45},
                {"sensor": "humidity", "op": "<=", "value": 20},
                {"sensor": "ldr", "op": "<", "value": 120}
            ],
            "associated": [
                {
                    "label": "hot_and_dry",
                    "allOf": [
                        {"sensor": "temp", "min": 38, "max": 42},
                        {"sensor": "humidity", "min": 0,  "max": 35}
                    ]
                }
            ]
        }

    # Individual anomaly rules via robust quantiles
    t_hi = quantile(temp, 95)   # top 5% temp considered high
    h_lo = quantile(hum, 5)     # bottom 5% humidity considered low
    l_lo = quantile(ldr, 5) if ldr else 120

    # Make them slightly conservative (expand by margins)
    t_hi = round(t_hi + 1.0, 2)
    h_lo = round(max(0.0, h_lo + 0.0), 2)
    l_lo = round(max(0.0, l_lo + 0.0), 0)

    # Associated anomaly: hot-and-dry region using top/bottom deciles
    t_a_min = round(quantile(temp, 90), 2)
    t_a_max = round(max(t_a_min, quantile(temp, 98)), 2)
    h_a_max = round(quantile(hum, 15), 2)

    arb = {
        "version": int(time.time()),
        "individual": [
            {"sensor": "temp", "op": ">=", "value": t_hi},
            {"sensor": "humidity", "op": "<=", "value": h_lo},
            {"sensor": "ldr", "op": "<",  "value": l_lo}
        ],
        "associated": [
            {
                "label": "hot_and_dry",
                "allOf": [
                    {"sensor": "temp", "min": t_a_min, "max": t_a_max},
                    {"sensor": "humidity", "min": 0,    "max": h_a_max}
                ]
            }
        ]
    }
    return arb

def main():
    temp = fetch_feed("temp", 1000)
    hum  = fetch_feed("humidity", 1000)
    # LDR may be optional
    try:
        ldr = fetch_feed("ldr", 1000)
    except:
        ldr = []

    arb = build_rules(temp, hum, ldr)

    with open("arb.json", "w", encoding="utf-8") as f:
        json.dump(arb, f, ensure_ascii=False, indent=2)

    print("Wrote arb.json version", arb["version"])

if __name__ == "__main__":
    main()
