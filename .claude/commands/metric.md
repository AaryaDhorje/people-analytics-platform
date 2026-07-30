Implement the metric named $ARGUMENTS.
Order of work, no deviation:
1. Quote the exact formula from docs/METRICS.md.
2. Write the pytest test against tests/fixtures/tiny_org.py with the expected
   value computed by hand — show me the arithmetic in a comment.
3. Run it, confirm it fails for the right reason.
4. Implement in the correct app/metrics/ module.
5. Run it, confirm green.
6. Expose the endpoint, register it, curl it, paste the response.
