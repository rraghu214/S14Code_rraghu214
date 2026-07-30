"""Turn 2 of the CCTV Investigator 3-turn flow — continues from
e2e_cctv_flow_turn1.py's saved state.json.

Turn 2: the user taps an incident card (its label carries the literal event
id, per turn 1's instruction) -> that event's FULL record (frame_url, boxes)
is folded into the prompt -> the agent should compose an AnnotatedImage of
the frame plus a DataTable of the other incidents for cross-reference.

Usage:
    uv run python scripts/e2e_cctv_flow_turn1.py   # first
    uv run python scripts/e2e_cctv_flow_turn2.py
"""
from __future__ import annotations

import json
from pathlib import Path
import re

import requests

BASE = "http://127.0.0.1:8113"
ROOT = Path(__file__).resolve().parents[1]
EVENTS = json.loads((ROOT / "s13code" / "ui" / "client" / "cctv" / "events.json").read_text())
OUT_DIR = ROOT / "scratch_verify" / "e2e"
STATE_PATH = OUT_DIR / "state.json"


def compact(ev: dict) -> dict:
    return {k: ev[k] for k in ("id", "camera", "time", "motion_zone", "summary", "severity")}


def main() -> None:
    state = json.loads(STATE_PATH.read_text())
    turn1 = json.loads((OUT_DIR / "turn1_composed.json").read_text())

    # Mirrors cctv_app.html's R.Button onclick: the label text IS the next
    # turn's user message (choose(lab) -> runTurn(lab)).
    buttons = [c for c in turn1["surface"]["components"] if c["type"] == "Button"]
    if not buttons:
        raise SystemExit("turn 1 composed no Button components to pick from — rerun turn1 first")
    picked_label = buttons[0]["label"]
    match = re.search(r"evt_\d{3}", picked_label)
    if not match:
        raise SystemExit(f"picked label {picked_label!r} has no literal event id — turn1's instruction wasn't followed")
    picked = next(e for e in EVENTS if e["id"] == match.group(0))
    print(f"[turn2] simulated tap on button: {picked_label!r} -> resolved to {picked['id']}")

    other = [compact(e) for e in EVENTS if e["id"] != picked["id"]]
    goal = (
        f"{state['turn1_goal']}\n"
        f'So far the user picked: "{picked_label}".\n\n'
        "Full record for the picked incident (bind frame_url to an AnnotatedImage's src prop "
        "and boxes to its boxes prop; caption can be the summary):\n"
        f"{json.dumps(picked, indent=2)}\n\n"
        "Other incidents across cameras, for cross-reference (render as a DataTable bound to "
        '/other_incidents, columns id/camera/time/summary):\n'
        f"{json.dumps({'other_incidents': other}, indent=2)}\n\n"
        "Compose an interface with: an AnnotatedImage of the picked incident's frame with its "
        "detection boxes overlaid, a short text summary, and a DataTable of the other incidents "
        'above. Also include one tappable choice/button literally labeled "notify" so the user '
        "can flag this incident for follow-up."
    )

    res = requests.post(
        f"{BASE}/v1/agent/runs",
        json={
            "prompt": goal, "respond_as": "ui",
            "tenant_id": "course", "project_id": "s14-cctv", "user_id": "investigator", "agent_id": "app",
        },
        timeout=90,
    )
    res.raise_for_status()
    run = res.json()
    run_id = run["run_id"]

    composed = requests.get(f"{BASE}/v1/runs/{run_id}/composed", timeout=30).json()
    (OUT_DIR / "turn2_run.json").write_text(json.dumps(run, indent=2))
    (OUT_DIR / "turn2_composed.json").write_text(json.dumps(composed, indent=2))

    types = [c.get("type") for c in composed.get("surface", {}).get("components", [])]
    print(f"[turn2] run_id={run_id} clean={composed.get('clean')} "
          f"components={composed.get('component_count')} provider={composed.get('provider')}")
    print(f"[turn2] component types: {types}")
    print(f"[turn2] rejections: {composed.get('rejections', [])}")
    print(f"[turn2] AnnotatedImage present: {'AnnotatedImage' in types}")

    state.update({
        "turn2_goal": goal,
        "picked_label": picked_label,
        "picked_event_id": picked["id"],
        "turn2_run_id": run_id,
    })
    STATE_PATH.write_text(json.dumps(state, indent=2))
    print(f"\nState updated in {STATE_PATH} — run e2e_cctv_flow_turn3.py next.")


if __name__ == "__main__":
    main()
