"""Turn 3 of the CCTV Investigator 3-turn flow — continues from
e2e_cctv_flow_turn2.py's saved state.json.

Turn 3: the user taps "notify" -> the agent should compose an ApprovalCard
whose params exactly match the incident being flagged (S14 §2.6 — the
binding invariant: approved args must match what was shown). After composing,
this script also exercises the real POST /v1/action call cctv_app.html's
approve() makes, proving the HITL check is genuine (matching args ->
approved; mismatched args -> refused).

Usage:
    uv run python scripts/e2e_cctv_flow_turn1.py   # first
    uv run python scripts/e2e_cctv_flow_turn2.py   # then
    uv run python scripts/e2e_cctv_flow_turn3.py
"""
from __future__ import annotations

import json
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8113"
ROOT = Path(__file__).resolve().parents[1]
EVENTS = json.loads((ROOT / "s13code" / "ui" / "client" / "cctv" / "events.json").read_text())
OUT_DIR = ROOT / "scratch_verify" / "e2e"
STATE_PATH = OUT_DIR / "state.json"


def main() -> None:
    state = json.loads(STATE_PATH.read_text())
    picked = next(e for e in EVENTS if e["id"] == state["picked_event_id"])
    picked_label = state["picked_label"]

    goal = (
        f"{state['turn1_goal']}\n"
        f'So far the user picked: "{picked_label}", then "notify".\n\n'
        "The user wants to flag this incident for follow-up:\n"
        f"{json.dumps(picked, indent=2)}\n\n"
        'Compose an ApprovalCard whose params is EXACTLY {"action":"notify",'
        f'"event_id":"{picked["id"]}","camera":"{picked["camera"]}","time":"{picked["time"]}"}} '
        "and whose summary explains a notification will be sent for this incident. This is the "
        "last step; do not add further choices."
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
    (OUT_DIR / "turn3_run.json").write_text(json.dumps(run, indent=2))
    (OUT_DIR / "turn3_composed.json").write_text(json.dumps(composed, indent=2))

    types = [c.get("type") for c in composed.get("surface", {}).get("components", [])]
    print(f"[turn3] run_id={run_id} clean={composed.get('clean')} "
          f"components={composed.get('component_count')} provider={composed.get('provider')}")
    print(f"[turn3] component types: {types}")
    print(f"[turn3] ApprovalCard present: {'ApprovalCard' in types}")

    approval = next((c for c in composed["surface"]["components"] if c["type"] == "ApprovalCard"), None)
    if approval is None:
        print("[turn3] no ApprovalCard composed — stopping before /v1/action checks")
        return

    dm = composed["surface"]["dataModel"]

    def resolve(v):
        if isinstance(v, dict) and "$bind" in v:
            ptr = v["$bind"].lstrip("/").split("/")
            cur = dm
            for p in ptr:
                cur = cur.get(p) if isinstance(cur, dict) else None
            return cur
        return v

    params = resolve(approval.get("params"))
    print(f"[turn3] ApprovalCard params resolved from dataModel: {params}")

    # Real POST /v1/action, matching args (S14 §2.6): should be approved.
    good = requests.post(f"{BASE}/v1/action", json={
        "run_id": run_id, "node_id": "surface", "action": "approve",
        "args": params, "pending_params": params,
        "pending_summary": resolve(approval.get("summary")) or "",
    })
    print(f"[turn3] matching-args /v1/action -> {good.status_code} {good.json()}")

    # Tampered args (S14 §2.6's binding invariant): should be refused (409).
    tampered = dict(params)
    tampered["camera"] = "vault"  # widened/altered scope
    bad = requests.post(f"{BASE}/v1/action", json={
        "run_id": run_id, "node_id": "surface", "action": "approve",
        "args": tampered, "pending_params": params,
        "pending_summary": resolve(approval.get("summary")) or "",
    })
    print(f"[turn3] tampered-args /v1/action -> {bad.status_code} {bad.text[:200]}")

    STATE_PATH.write_text(json.dumps({**state, "turn3_run_id": run_id}, indent=2))
    print(f"\nFull 3-turn flow complete. All request/response JSON saved under {OUT_DIR}.")


if __name__ == "__main__":
    main()
