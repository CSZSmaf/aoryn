from desktop_agent.browser_dom import dom_backend_status


def test_dom_backend_status_reports_missing_or_available_backend():
    status = dom_backend_status("playwright")

    assert status.backend == "playwright"
    assert isinstance(status.available, bool)
    assert status.detail
