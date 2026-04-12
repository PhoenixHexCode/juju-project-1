# JUJU — AI Companion

A voice-first, **LLM-agnostic** AI companion that runs anywhere — phone, tablet,
laptop, server — installs as a PWA, remembers every conversation, and spawns
parallel expert sub-agents on demand to handle complex requests.

> **Personality**, not impersonation. JUJU's tone is written to *read* like a
> witty, sarcastic, fast-talking genius. The TTS voice is rendered through a
> configurable ElevenLabs voice ID that **you** must point at a voice you
> legally own or license. JUJU will not, and should not, clone the voice of
> any real human being.

---

## What it does

| Feature | How |
|---|---|
| **LLM-agnostic** | A scoring router picks the best available provider per request from Anthropic, OpenAI, Google, Groq, and Mistral. Falls through to the next-best on failure. |
| **Voice in / voice out** | `faster-whisper` (local) or OpenAI Whisper for STT; ElevenLabs for TTS. |
| **Persistent memory** | SQLite journal of every turn + Chroma vector index for semantic recall. |
| **Recursive agent swarm** | A root agent decides when to delegate. Sub-agents can spawn their own sub-agents. Hard caps on depth, fanout, and total spawn count. |
| **Device-aware MCP server** | Detects whether it's running on a desktop, server, or phone-PWA host and exposes only tools that make sense (fs, shell, browser, host bridge, …). |
| **Remote home-PC bridge** | A small token-authenticated FastAPI server (`tools/host_bridge_server.py`) you run on your home machine. JUJU calls it to scaffold projects, run builds, launch dev servers. |
| **Permission broker** | When an agent needs a capability you haven't granted, JUJU asks via WebSocket / voice with `allow once / session / always / deny` options. Auto-denies if nobody answers. |
| **Installable PWA** | The frontend is a service-worker-backed PWA. Add to home screen on iOS/Android, or install as an app on desktop Chromium/Edge/Safari. |
| **Reference skills** | `BookingCallSkill` (Twilio outbound call with mandatory AI disclosure) and `AppBuilderSkill` (drives the host bridge to scaffold/test/serve a new app). |

---

## Architecture

```
                  ┌──────────────────────────────────────────────┐
                  │                  PWA / CLI                   │
                  │  mic capture · TTS playback · perm dialog    │
                  └──────────────┬───────────────────────────────┘
                                 │  WebSocket (audio + JSON events)
                                 ▼
   ┌──────────────────────────────────────────────────────────────┐
   │                        FastAPI app                            │
   │  /api/auth /api/chat /api/memory /api/tools /api/ws/voice    │
   └──────────────┬───────────────────────────────────────────────┘
                  ▼
            ┌──────────┐
            │ Companion│  ← single object held in app.state
            └────┬─────┘
                 │
   ┌─────────────┼──────────────┬──────────────┬───────────────┐
   ▼             ▼              ▼              ▼               ▼
LLMRouter    MemoryStore    Orchestrator    MCP Tools     Voice I/O
 (5 prov.)   SQLite+Chroma  recursive       fs/shell/     STT + TTS
                            agents          browser/      (persona)
                                            host bridge
                                                  │
                                                  ▼
                                       ┌─────────────────────┐
                                       │  Host Bridge server │
                                       │ (your home machine) │
                                       └─────────────────────┘
```

### Recursive agent flow (the "book a restaurant" example)

```
root agent
 ├── calendar-agent       (when am I free in the next 7 days?)
 ├── restaurant-agent     (best places within driving radius)
 └── booking-agent        ← spawned after the first two return
      └── BookingCallSkill (Twilio outbound call, AI disclosure first)
```

The orchestrator caps each fan-out at `AGENT_MAX_PARALLEL` (default 5) and
each branch at `AGENT_MAX_DEPTH` (default 3), with a per-request timeout.

---

## Quick start

### 1. Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add at least one LLM API key. Everything else (ElevenLabs,
Twilio, host bridge) is optional and degrades gracefully.

### 2. Run the backend + PWA

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000` on your phone or laptop, type a name to log in,
and start talking. On iOS Safari and Android Chrome you can "Add to Home
Screen" to install JUJU as a real app.

### 3. Headless (CLI) mode

```bash
python tools/cli.py
```

### 4. Run the host bridge on your home computer (optional)

This is what lets JUJU drive your personal machine when you're on the road.

```bash
# on the home computer:
export HOST_BRIDGE_TOKEN=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
python tools/host_bridge_server.py
```

Expose it via Tailscale Funnel / Cloudflare Tunnel / Caddy + HTTPS, then in
your companion `.env`:

```
HOST_BRIDGE_URL=https://my-home-pc.example.com:9090
HOST_BRIDGE_TOKEN=<the same token>
```

The host bridge sandboxes file/shell actions inside `~/companion-projects` by
default. Edit `tools/host_bridge_server.py` to widen or narrow that.

---

## Tests

```bash
pytest
```

The suite uses fake LLM providers and a temporary SQLite db, so it runs offline
and needs zero API keys.

---

## Project layout

```
backend/
  config.py                  pydantic settings
  companion.py               wires router + memory + agents + mcp + voice
  main.py                    FastAPI entrypoint
  llm/
    router.py                provider scoring + fallthrough
    providers/               anthropic / openai / google / groq / mistral
  memory/store.py            SQLite + Chroma
  voice/
    persona.py               personality definition
    stt.py                   faster-whisper / OpenAI Whisper
    tts.py                   ElevenLabs
  agents/
    orchestrator.py          global caps + spawning
    expert.py                recursive expert agent
  mcp_server/
    device.py                detect host kind
    server.py                tool registry (fs/shell/browser/bridge)
    host_bridge.py           remote home-PC client
  security/
    auth.py                  JWT + bcrypt
    permissions.py           voice-friendly elevation broker
  api/routes.py              REST + WebSocket
  skills/
    booking_call.py          Twilio outbound call (with disclosure)
    app_builder.py           remote scaffold / test / serve

frontend/                    installable PWA
tools/
  cli.py                     headless terminal client
  host_bridge_server.py      run on your home computer
tests/                       offline pytest suite
```

---

## Important safety notes

1. **No celebrity voice cloning.** ElevenLabs (and any reputable TTS provider)
   prohibits cloning a real person's voice without consent. JUJU's persona is
   personality-only; the voice timbre comes from a voice ID you supply and own.

2. **AI disclosure on outbound calls.** `BookingCallSkill` injects an
   "automated assistant calling on behalf of …" line at the start of every
   call. Don't remove it. Several US states (and an FCC ruling in 2024) require
   disclosure that the caller is AI.

3. **Permission broker auto-denies when no UI is attached.** If you run JUJU
   headless without wiring up a permission listener, no agent can read files,
   run shell commands, or hit the host bridge. This is the intended fail-safe.

4. **The host bridge token is the only credential between JUJU and your home
   computer.** Use HTTPS, rotate the token if it leaks, and keep
   `HOST_BRIDGE_ROOT` pointed at a project directory you don't mind being
   modified.

5. **MVP, not production.** This is a working skeleton you can run and extend.
   Auth is intentionally permissive (any non-empty username gets a token) so
   you can test on a LAN immediately — replace it before exposing to the open
   internet.
