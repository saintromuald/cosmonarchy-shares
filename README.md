# Cosmonarchy Shares & Bug Reports

Public board for Cosmonarchy community shares, and the home of the
**crash-report pipeline**:

1. Players press **Share recent logs** in the Cosmonarchy Plus Launcher
   (Config tab) — the launcher packages the recent logs, crash captures,
   replays, build identity and configs, and publishes them under
   `crash-reports/<timestamp>/`.
2. The **auto-triage bot** (`.github/workflows/auto-triage.yml`) pairs the
   two sides of the same game, compares them mechanically (build/plugin/
   config identity, the game's own desync records, crash signatures), and
   writes `diagnosis.md` into both reports with the routing decision:
   - **FLASH lane** — a mechanical difference is the cause; a cheap model
     can explain and fix it.
   - **DEEP lane** — both sides identical; the divergence is in the engine
     or plugins. The diagnosis includes the prompt to hand a stronger model.
3. `crash-reports/INDEX.md` lists every report and its state.
