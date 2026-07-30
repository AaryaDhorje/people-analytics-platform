Run the full verification suite and report results as a table:
1. cd backend && ruff check .
2. cd backend && pytest -q
3. cd frontend && npm run build
4. Hit every registered endpoint with curl against the local server and report
   HTTP status + whether `data` is non-empty.
Report failures with file and line. Fix nothing unless I say so.
