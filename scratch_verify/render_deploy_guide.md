# Render deployment guide — glc_v3 gateway + S14Code CCTV app

Two separate Render Web Services. Create the gateway first (you need its
public URL for the second service's GLC_BASE_URL).

## Service 1 — glc_v3 gateway

1. Render dashboard -> New -> Web Service.
2. Source: "Public Git Repository" -> `https://github.com/theschoolofai/glc_v3`
   (no fork needed, it's public — matches §0 of the plan).
3. Branch: `main` (or whatever glc_v3's default branch is).
4. Environment: Python 3.
5. Build Command: `pip install uv && uv sync --frozen`
6. Start Command: `uv run glc serve --port $PORT`
7. Environment variables (Render dashboard -> Environment -> Add — copy
   VALUES from your local `glc_v3/.env`, never paste secrets into chat):
   - `GEMINI_API_KEY`
   - `GROQ_API_KEY`
   - `TAVILY_API_KEY`
   - `NVIDIA_API_KEY`
   - `CEREBRAS_API_KEY`
   - `OPEN_ROUTER_API_KEY`
   - `GITHUB_ACCESS_TOKEN`
   - `LLM_ORDER` (same value as your local `.env`)
   - `GEMINI_MODEL` = `gemini-3.1-flash-lite-preview` (gemini-2.5-flash was
     confirmed live to be slow — 26-28s/call — and to truncate JSON output
     repeatedly on this app's larger CCTV-shaped prompts; gemini-3.1-flash-
     lite-preview was verified end-to-end today: every call succeeded on the
     first attempt at 1.3-2.4s. Set at the gateway level, per glc_v3's own
     `providers.py:1176` — S14Code specifies no model at all, by design.)
8. Deploy. Once live, note the public URL, e.g.
   `https://glc-v3-xxxx.onrender.com` — needed for Service 2.
9. Sanity check: `curl https://<glc-v3-url>.onrender.com/v1/providers` should
   list the same providers as local (`cerebras, gemini, github, openrouter,
   groq, nvidia, ollama` in the `order` field — `ollama` will simply never
   succeed since there's no Ollama reachable from Render, which is fine,
   it's last in the failover order and not required).

## Service 2 — S14Code (CCTV app)

1. Render dashboard -> New -> Web Service.
2. Source: connect your GitHub account -> `rraghu214/S14Code_rraghu214`.
3. Branch: `part2-cctv-investigator` (NOT main, NOT s14-annotated-image —
   this is the branch with both AnnotatedImage and all Part 2 code).
4. Environment: Python 3.
5. Build Command: `pip install uv && uv sync --frozen`
6. Start Command: `uv run s13code serve --port $PORT`
   (the CLI entry point is `s13code.cli:main`, registered under both the
   `s13code` and `s14code` script names — either works, `s13code` shown here
   since that's the literal package/module name).
7. Environment variables:
   - `GLC_BASE_URL` = the Service 1 URL from above (e.g.
     `https://glc-v3-xxxx.onrender.com`)
   - `S13_GATEWAY_PROVIDER` = `` (empty string — enables glc_v3's own full
     auto-failover across all configured providers; see runtime.py comments
     — this is deliberate, not an oversight, confirmed live today: pinning
     a single provider left no recovery path when one provider's quota was
     exhausted)
   - `S13_SANDBOX_ROOT` = `/opt/render/project/src/sandbox` (an absolute
     path Render's filesystem will accept — the exact directory name doesn't
     matter, it just needs to be absolute and writable)
   - `S13_LIVE_SEMANTIC_CHUNKING` = `0` (verified safe today — drops the
     Ollama dependency entirely; see scratch_verify/pr_writeup_notes.md #7
     if that section gets added, or the live smoke test done during this
     session)
   - `S13_A2A_GRPC_ENABLED` = `0` (unused by this app; Render's free web
     service only exposes one port anyway)
   - `S14_SURFACE_MAX_TOKENS` = `6000`
   - `S13_ANSWER_MAX_TOKENS` = `2000`
   - `S14_SURFACE_TEMPERATURE` = `0.2` (optional — this is already the
     runtime.py default, only set it if you want a different value)
   - `S14_SURFACE_RETRIES` = `3` (optional — already the default)
   - No model variable here — S14Code intentionally specifies no model
     anywhere in its own payloads (see GEMINI_MODEL under Service 1 above;
     glc_v3 owns that decision, not S14Code).
8. Deploy. Once live: open `https://<your-app>.onrender.com/investigator`
   in a browser and run all 3 turns.

## Before the final incognito test (submission requirement)

- Render's free tier sleeps a service after ~15 min idle; the first request
  after that can take 30-60s+ while it wakes. Visit both URLs once to warm
  them up, THEN do the actual incognito test run — don't let the graded
  first-impression be a cold start.
- Confirm `/cctv/frames/e1.jpg` (etc.) load directly — proves the static
  image mount survived the deploy.
- Run all 3 turns for real in the incognito window, exactly as you'll
  describe in the PR write-up.
