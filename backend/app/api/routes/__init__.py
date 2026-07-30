"""Route modules, one per metric domain plus health and the AI endpoints.

Each router is registered in app/main.py. Routes stay thin: parse and validate
input, call into app/metrics/, wrap the result in the standard envelope.
"""
