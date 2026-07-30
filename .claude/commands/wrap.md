End-of-phase wrap:
1. Run /verify.
2. Append a section to docs/SESSION_LOG.md for this phase (create the file if it does
   not exist). Use this shape, one paragraph per bullet, specific not generic:
   - **Phase N — <name>** and the elapsed-hour range.
   - **Prompt strategy:** what you were asked to do and how the work was framed —
     plan mode, which subagents, what context was deliberately excluded.
   - **Accepted:** what was kept, and why it was the right call.
   - **Rejected:** plans, approaches, or generated code that was thrown away, and the
     reason. Be concrete. This is the most valuable part of the log — it is what shows
     judgement rather than autocomplete, and it feeds the README's "how it was built"
     section and the Loom notes.
   - **Numbers:** files changed, tests passing, endpoints live.
3. Update docs/ARCHITECTURE.md if the architecture changed.
4. git add -A and commit with a conventional-commit message describing the phase.
   Keep the Claude co-author trailer on the commit.
5. Print: files changed, tests passing count, endpoints live, next phase, blockers.
