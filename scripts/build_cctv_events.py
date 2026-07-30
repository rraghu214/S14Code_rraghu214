"""Build s13code/ui/client/cctv/events.json from the staged CCTV frames.

Calls glc_v3's POST /v1/vision once per frame with a strict JSON schema for
typed bounding-box output, so detections are real model output, not
hand-authored guesses. Camera/timestamp/motion_zone metadata is reused from
the original Session-3 events.json (verified against the burned-in overlay
text on each frame); only summary + boxes come fresh from the vision call.

Usage:
    uv run python scripts/build_cctv_events.py
"""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

import requests

GLC_BASE_URL = os.getenv("GLC_BASE_URL", "http://127.0.0.1:8111")
ROOT = Path(__file__).resolve().parents[1]
FRAMES_DIR = ROOT / "s13code" / "ui" / "client" / "cctv" / "frames"
OUT_PATH = ROOT / "s13code" / "ui" / "client" / "cctv" / "events.json"

# camera / timestamp / motion_zone verified against each frame's burned-in
# overlay text (CAM-0X ZONE + timestamp), not against the old fictional
# .caption.txt files. See s14_assignment_FINAL_v2.md §2.3.
EVENTS_META = [
    {"id": "evt_001", "camera": "gate", "time": "2026-04-23T12:14:03", "motion_zone": "entrance", "frame": "e1.jpg"},
    {"id": "evt_002", "camera": "driveway", "time": "2026-04-23T12:14:28", "motion_zone": "path", "frame": "e2.jpg"},
    {"id": "evt_003", "camera": "porch", "time": "2026-04-23T12:14:52", "motion_zone": "door", "frame": "e3.jpg"},
    {"id": "evt_004", "camera": "porch", "time": "2026-04-23T12:15:41", "motion_zone": "door", "frame": "e4.jpg"},
    {"id": "evt_005", "camera": "driveway", "time": "2026-04-23T12:16:08", "motion_zone": "path", "frame": "e5.jpg"},
    {"id": "evt_006", "camera": "gate", "time": "2026-04-23T12:16:32", "motion_zone": "exit", "frame": "e6.jpg"},
    {"id": "evt_007", "camera": "backyard", "time": "2026-04-23T14:02:11", "motion_zone": "fence", "frame": "e7.jpg"},
]

BOX_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "One factual sentence describing what is actually visible in the frame.",
        },
        "severity": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "description": "Rough incident severity: low=routine/benign, medium=worth a look, high=needs attention.",
        },
        "boxes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "x": {"type": "number", "description": "left edge, % of image width, 0-100"},
                    "y": {"type": "number", "description": "top edge, % of image height, 0-100"},
                    "w": {"type": "number", "description": "box width, % of image width, 0-100"},
                    "h": {"type": "number", "description": "box height, % of image height, 0-100"},
                    "label": {"type": "string"},
                    "confidence": {"type": "number", "description": "0-1"},
                },
                "required": ["x", "y", "w", "h", "label", "confidence"],
            },
        },
    },
    "required": ["summary", "severity", "boxes"],
}

PROMPT = (
    "This is a black-and-white CCTV frame. Detect every person, animal, or notable object "
    "actually visible in the image. For each, return a bounding box as PERCENTAGES (0-100) of "
    "the image width/height: x = left edge %, y = top edge %, w = width %, h = height %. "
    "Ignore the green burned-in camera-id/timestamp text overlay in the corners — it is not a "
    "detection target. Be precise about what is actually in the frame; do not invent people or "
    "objects that are not visible. Also give a one-sentence factual summary of the frame and a "
    "rough severity (low/medium/high)."
)


def to_data_url(path: Path) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def call_vision(image_path: Path, retries: int = 5) -> dict:
    payload = {
        "image": to_data_url(image_path),
        "prompt": PROMPT,
        "schema": BOX_SCHEMA,
        "schema_name": "cctv_detection",
        # No "provider" pinned: omitting it lets glc_v3 auto-restrict
        # candidates to whichever configured providers actually have the
        # "vision" capability (glc/routes/chat.py:272-283) and fail over
        # between them — per /v1/capabilities only gemini_1 and github
        # (gpt-4.1-mini) qualify. Pinning "gemini" here previously blocked
        # that failover and we burned gemini's 15 RPM ceiling with no
        # fallback.
        "temperature": 0.2,
        # A busy frame can produce many boxes; too small a budget truncates
        # the JSON mid-string and glc_v3 returns 503 "output is not JSON".
        "max_tokens": 2048,
    }
    last_err: Exception | None = None
    for attempt in range(retries):
        resp = requests.post(f"{GLC_BASE_URL}/v1/vision", json=payload, timeout=60)
        if resp.status_code == 200:
            body = resp.json()
            # "parsed" is set by glc_v3 whenever response_format/schema was
            # used (glc/llm_schemas.py:120) — prefer it over re-parsing text.
            return body.get("parsed") or json.loads(body.get("text", ""))
        last_err = requests.exceptions.HTTPError(f"{resp.status_code}: {resp.text[:300]}")
        # gemini_1's per-minute RPM quota needs real wall-clock time to
        # recover, not a short backoff — the gateway's own error names the
        # remaining cooldown (e.g. "RPM quota burned (56s left)").
        wait = 65 if "RPM quota" in resp.text else 5 * (attempt + 1)
        print(f"\n  retry {attempt + 1}/{retries} after {wait}s ({resp.text[:150]})", end=" ")
        time.sleep(wait)
    raise last_err


def main() -> None:
    done: dict[str, dict] = {}
    if OUT_PATH.exists():
        for ev in json.loads(OUT_PATH.read_text()):
            done[ev["id"]] = ev

    events = []
    for meta in EVENTS_META:
        if meta["id"] in done:
            print(f"[vision] {meta['frame']} ... skipped (already have {meta['id']})")
            events.append(done[meta["id"]])
            continue
        frame_path = FRAMES_DIR / meta["frame"]
        print(f"[vision] {meta['frame']} ...", end=" ", flush=True)
        detection = call_vision(frame_path)
        boxes = detection.get("boxes", [])
        print(f"{len(boxes)} box(es), severity={detection.get('severity')}")
        events.append({
            "id": meta["id"],
            "camera": meta["camera"],
            "time": meta["time"],
            "motion_zone": meta["motion_zone"],
            "summary": detection.get("summary", ""),
            "severity": detection.get("severity", "low"),
            "frame_url": f"/cctv/frames/{meta['frame']}",
            "boxes": boxes,
        })
        OUT_PATH.write_text(json.dumps(events, indent=2))  # incremental save, survives a mid-run crash
    OUT_PATH.write_text(json.dumps(events, indent=2))
    print(f"\nWrote {len(events)} events to {OUT_PATH}")


if __name__ == "__main__":
    main()
