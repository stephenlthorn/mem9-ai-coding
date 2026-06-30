"""Pytest config for the offline unit suite.

These tests exercise the parts of the system that are deterministic without
network or credentials: topology/namespacing, the checked-in repo manifests,
the offline embedding fallback, and transitive dependency traversal over the
manifest graph. Live mem9 behavior (hybrid search, writes, team isolation, the
MCP stdio server) is exercised against a real mem9 space via the dashboard and
the 3-CLI demo, not in this unit suite.
"""
