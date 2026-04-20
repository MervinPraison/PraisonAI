"""
Tests for G-C: Skills observability events.
"""

from praisonaiagents.skills.events import SkillDiscoveredEvent, SkillActivatedEvent


def test_skill_discovered_event():
    """Test SkillDiscoveredEvent structure and fields."""
    event = SkillDiscoveredEvent(
        agent="test-agent",
        skill_name="pdf-processing", 
        source="/home/user/skills",
        description_chars=145
    )
    
    assert event.agent == "test-agent"
    assert event.skill_name == "pdf-processing"
    assert event.source == "/home/user/skills"
    assert event.description_chars == 145


def test_skill_activated_event():
    """Test SkillActivatedEvent structure and fields."""
    event = SkillActivatedEvent(
        agent="test-agent",
        skill_name="pdf-processing",
        trigger="slash",
        arguments="input.pdf output.txt",
        rendered_chars=1250,
        session_id="sess_123",
        activation_time_ms=45.2
    )
    
    assert event.agent == "test-agent"
    assert event.skill_name == "pdf-processing" 
    assert event.trigger == "slash"
    assert event.arguments == "input.pdf output.txt"
    assert event.rendered_chars == 1250
    assert event.session_id == "sess_123"
    assert event.activation_time_ms == 45.2


def test_skill_activated_event_optional_fields():
    """Test SkillActivatedEvent with optional fields omitted."""
    event = SkillActivatedEvent(
        agent="test-agent",
        skill_name="web-scraper",
        trigger="activate_tool",
        arguments="https://example.com",
        rendered_chars=890
    )
    
    assert event.agent == "test-agent"
    assert event.skill_name == "web-scraper"
    assert event.trigger == "activate_tool" 
    assert event.arguments == "https://example.com"
    assert event.rendered_chars == 890
    assert event.session_id is None
    assert event.activation_time_ms is None


def test_skill_activated_event_trigger_types():
    """Test all valid trigger types for SkillActivatedEvent."""
    valid_triggers = ["slash", "activate_tool", "auto"]
    
    for trigger in valid_triggers:
        event = SkillActivatedEvent(
            agent="agent",
            skill_name="skill",
            trigger=trigger,
            arguments="",
            rendered_chars=100
        )
        assert event.trigger == trigger