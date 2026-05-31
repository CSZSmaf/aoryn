from desktop_agent.composer import DocumentArtifact, DocumentComposer, parse_document_text
from desktop_agent.config import AgentConfig


def _offline_config() -> AgentConfig:
    # composition_enabled=False forces the deterministic fallback, so the test
    # never depends on a reachable model endpoint.
    return AgentConfig(composition_enabled=False)


def test_compose_fallback_builds_structured_document_from_notes():
    composer = DocumentComposer(_offline_config())
    artifact = composer.compose(
        goal="plan a 3 day Beijing trip and write it into Word",
        notes=[
            "[web] Beijing travel guide - https://example.com/beijing",
            "[web] Day 1: Forbidden City and Tiananmen Square are must-see spots.",
        ],
    )
    assert isinstance(artifact, DocumentArtifact)
    assert artifact.source == "fallback"
    assert artifact.title
    assert len(artifact.sections) >= 2
    plain = artifact.to_plain_text()
    assert "Forbidden City" in plain
    assert "https://example.com/beijing" in plain


def test_compose_fallback_chinese_goal_uses_chinese_scaffold():
    composer = DocumentComposer(_offline_config())
    artifact = composer.compose(goal="规划北京三日游计划", notes=["[web] 故宫、天安门是必去景点"])
    plain = artifact.to_plain_text()
    assert "概述" in plain
    assert "故宫" in plain


def test_compose_fallback_without_notes_still_produces_document():
    composer = DocumentComposer(_offline_config())
    artifact = composer.compose(goal="write a short report about renewable energy", notes=[])
    assert artifact.sections
    assert artifact.to_plain_text().strip()


def test_parse_document_text_extracts_title_and_sections():
    content = (
        "# Beijing 3-Day Itinerary\n"
        "\n"
        "## Day 1\n"
        "Visit the Forbidden City in the morning.\n"
        "\n"
        "## Day 2\n"
        "- Great Wall at Mutianyu\n"
        "- Summer Palace\n"
    )
    artifact = parse_document_text(content, goal="beijing trip")
    assert artifact is not None
    assert artifact.title == "Beijing 3-Day Itinerary"
    headings = [section.heading for section in artifact.sections]
    assert "## Day 1" in headings
    assert "## Day 2" in headings


def test_parse_document_text_handles_plain_body_without_headings():
    artifact = parse_document_text("Just a single paragraph of useful content.", goal="note")
    assert artifact is not None
    assert artifact.sections
    assert "useful content" in artifact.to_plain_text()


def test_parse_document_text_returns_none_for_empty():
    assert parse_document_text("", goal="x") is None
    assert parse_document_text("   \n  ", goal="x") is None


def test_compose_fallback_keeps_urls_out_of_key_points():
    artifact = DocumentComposer(_offline_config()).compose(
        goal="写一份关于电动汽车的报告",
        notes=["[web] 电动汽车 - https://www.google.com/search?q=ev", "[extract] 续航提升与充电网络扩张推动增长", "[web] https://example.com/ev"],
    )
    key_points = next((s.body for s in artifact.sections if "要点" in s.heading or "Key" in s.heading), "")
    assert "http" not in key_points
    assert "续航提升" in key_points
    sources = next((s.body for s in artifact.sections if "来源" in s.heading or "Sources" in s.heading), "")
    assert "https://example.com/ev" in sources
