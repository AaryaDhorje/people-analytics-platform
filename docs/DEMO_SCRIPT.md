# Loom script — 4:30 target

Recorded in phase 8. Beats and timings are fixed here so the recording doesn't get
improvised; the planted scenarios in §3 of `BUILD_PLAN.md` are what each beat points at.

| Time | Beat | On screen |
|---|---|---|
| 0:00–0:30 | The problem: HR teams have data in six systems and answer questions in spreadsheets weeks late. This gives them the answer in one screen. | Overview page, live |
| 0:30–1:00 | Architecture in 30 seconds: Postgres star schema → SQL views → FastAPI metric services → React → Claude layer on top. 1,850 employee records, 3 years, all synthetic. | Mermaid architecture diagram |
| 1:00–1:30 | Talent Acquisition: the Sales interview bottleneck in the funnel, then the source-effectiveness scatter. Say the line: *agency is our most expensive channel and our worst-retaining one.* | Acquisition page |
| 1:30–2:30 | Retention — spend the most time here. Attrition trend, the manager heatmap surfacing M-114, then the flight-risk table; expand one employee and read the reasons aloud. | Retention page |
| 2:30–3:00 | Engagement: eNPS trend, the post-reorg dip in Belonging, the engagement-quartile vs attrition chart proving the lag. Show Claude-extracted comment themes. | Engagement page |
| 3:00–3:20 | Productivity: the Support burnout story — overtime up, utilization over 95%, workload driver lowest. Tie it back to the attrition chart. | Productivity page |
| 3:20–4:00 | Ask the data: type *"which managers have the highest regretted attrition this year?"* Show the generated SQL. Emphasize it's auditable, view-scoped, and read-only. | Ask page |
| 4:00–4:30 | How it was built: ~80% authored by Claude Code. Show CLAUDE.md, the metric-verifier output, the test suite passing. One honest sentence on what's out of scope. | Terminal + CLAUDE.md |

## Recording notes

- **Write the opening and closing sentences out and read them.** Improvised intros eat
  40 seconds.
- One take, page already warm.
- Zoom to 125% so numbers are legible in playback.
- **Hit the deployed URL 2 minutes before recording.** Render free-tier cold start is
  ~50s and it will happen on camera otherwise.
- Have a local fallback recording ready in case the deploy misbehaves.

## The honest closing sentence

Name what's out of scope rather than letting it be discovered: no real auth (single demo
bearer token), synthetic data only, flight risk is a transparent weighted score and not a
trained model.
