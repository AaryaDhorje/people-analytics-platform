"""Claude-powered features. Populated in phase 6.

- nl_query.py   natural language to SQL: SELECT only, allowlisted views only,
                mandatory LIMIT, generated SQL returned to the caller so every
                answer is auditable.
- narrative.py  executive summary over the current filter context, and the
                plain-English explanation of an individual flight-risk score.
- comments.py   batch theme + sentiment classification of open-text survey
                comments, cached in a table so the dashboard never blocks on a
                live API call.

Every feature here degrades to a clear message if the API call fails. The demo
cannot show a stack trace.
"""
