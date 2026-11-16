# ShopAssist — Mini-Project 1

Order support for Northwind Store (a fictional online store): a FastAPI service with per-session memory, three
validated tools, a defended system prompt and streamed answers. The model is reached only through a LiteLLM
gateway, and both run together with Docker Compose.

**Author:** Anurag Sharma(Anurag-0905)

**Model tested:** `shopassist` → `groq/gpt-oss-20b` (with fallback to `shopassist-backup` → `groq/gpt-oss-120b`)
## Architecture

```
browser / client ──► app (FastAPI, :8000) ──► litellm gateway (:4000) ──► Groq
                     memory · prompt · tools    master key · fallback · cost      API_KEY lives only here
```

## API

| Method | Path | What it does |
|---|---|---|
| GET | `/health` | Liveness, plus the running model, gateway, memory strategy and tools |
| POST | `/chat` | `{"session_id", "message"}` → `{"answer", "tool_steps", "turns"}` |
| POST | `/chat/stream` | The same, streamed as Server-Sent Events: `tool`, `token`…, `done` |
| DELETE | `/sessions/{id}` | Forget one conversation |

## Run with Docker Compose (Path A)

```powershell
docker compose up --build        # gateway + app; Ctrl+C to stop, docker compose down to remove
```
Then open http://localhost:8000/docs. To verify the service is running, navigate to `http://localhost:8000/health` in your browser; you should see a JSON response confirming the API is "ok" along with your active memory strategy and loaded tools.

## Run without Docker (Path B)

```powershell
uv sync
# terminal 1 - the gateway
uv run --with "litellm[proxy]==1.80.0" litellm --config gateway/config.yaml --port 4000
# terminal 2 - the app
uv run uvicorn app.main:app --port 8000
```

## Evidence

```powershell
uv run python eval/run_eval.py    
```
Results:
golden: 9/10
golden_right_tools: 9/10
memory: pass
attacks_resisted: 3/4.
Discussion: `experiments/mp1_report.md`.

## Design

To manage context effectively, the system utilizes a sliding window memory strategy, which guarantees bounded token costs and zero additional LLM latency overhead by retaining only the most recent conversation turns. It equips the LLM with three specialized tools—for checking order status, estimating delivery, and determining return eligibility—which aggressively validate inputs via regex and catch bad arguments by returning ValueErrors that seamlessly prompt the LLM to ask the customer for correct formatting. The system prompt actively defends against prompt injection and role-play spoofing by enforcing a strict instruction hierarchy, neutralizing smuggled XML tags, and ensuring only authentically executed tool payloads are trusted. A robust gateway layer wraps this execution loop, cleanly routing inputs to the AI, maintaining session state, and exposing the active runtime configuration for seamless system auditing. The biggest known limitation of this architecture is the inherent fragility of smaller 20B models, which still require hardcoded deterministic overrides in the execution loop to completely prevent routing hallucinations and ensure precise string outputs. 