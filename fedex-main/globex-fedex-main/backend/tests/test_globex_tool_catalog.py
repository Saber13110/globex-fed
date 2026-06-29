"""Catalogue outils Globex Agent — 62 outils avec handlers."""

from app.services.globex_agent.tool_catalog import assert_catalog_complete, catalog_summary


def test_globex_tool_catalog_complete():
    summary = catalog_summary()
    assert summary["registered_count"] >= summary["target_count"]
    assert summary["missing_handlers"] == []
    assert_catalog_complete()
