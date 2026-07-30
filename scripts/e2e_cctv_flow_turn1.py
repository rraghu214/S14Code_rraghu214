"""Turn 1 of the CCTV Investigator 3-turn flow, run directly against the live
S14 runtime (http://127.0.0.1:8113) — same request shape cctv_app.html's
buildGoal()/runTurn() use (s13code/ui/client/cctv_app.html), just scripted so
each turn's request/response is reproducible and inspectable outside the
browser.

Turn 1: a vague question -> locally filtered events.json matches folded into
the prompt -> the agent composes selectable incident cards.

Saves conversation state to scratch_verify/e2e/state.json for
e2e_cctv_flow_turn2.py to continue from.

Usage:
    uv run python scripts/e2e_cctv_flow_turn1.py
"""
from __future__ import annotations

import json
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8113"
ROOT = Path(__file__).resolve().parents[1]
EVENTS = json.loads((ROOT / "s13code" / "ui" / "client" / "cctv" / "events.json").read_text())
OUT_DIR = ROOT / "scratch_verify" / "e2e"
OUT_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = OUT_DIR / "state.json"

USER_QUESTION = "did anything unusual happen near the gate yesterday?"


def compact(ev: dict) -> dict:
    return {k: ev[k] for k in ("id", "camera", "time", "motion_zone", "summary", "severity")}


def main() -> None:
    gate_events = [e for e in EVENTS if e["camera"] == "gate"]
    goal = (
        f'User asked: "{USER_QUESTION}"\n\n'
        "Matching incident records (from local search over a CCTV events log):\n"
        f"{json.dumps([compact(e) for e in gate_events], indent=2)}\n\n"
        "Compose an interface showing these as selectable incident cards (thumbnail-style: "
        "camera, time, a one-line summary, a StatTile for severity). Each card's tappable "
        'choice label MUST include the literal event id (e.g. "evt_003") somewhere in its '
        "text, verbatim, so it can be identified later. Do not fabricate any incident not "
        "listed above."
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
    (OUT_DIR / "turn1_run.json").write_text(json.dumps(run, indent=2))
    (OUT_DIR / "turn1_composed.json").write_text(json.dumps(composed, indent=2))

    types = [c.get("type") for c in composed.get("surface", {}).get("components", [])]
    print(f"[turn1] run_id={run_id} clean={composed.get('clean')} "
          f"components={composed.get('component_count')} provider={composed.get('provider')}")
    print(f"[turn1] component types: {types}")
    print(f"[turn1] rejections: {composed.get('rejections', [])}")

    STATE_PATH.write_text(json.dumps({
        "turn1_goal": goal,
        "user_question": USER_QUESTION,
        "turn1_run_id": run_id,
    }, indent=2))
    print(f"\nState saved to {STATE_PATH} — run e2e_cctv_flow_turn2.py next.")


if __name__ == "__main__":
    main()
