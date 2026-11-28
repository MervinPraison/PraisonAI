"""CrewAIAdapter reports a missing ``roles`` section clearly (#6714)."""

import pytest

from praisonai.framework_adapters.crewai_adapter import CrewAIAdapter


@pytest.mark.parametrize("config", [{}, {"roles": {}}, {"roles": None}])
def test_build_crew_without_roles_raises_value_error(config):
    with pytest.raises(ValueError, match="no agents defined under 'roles:'"):
        CrewAIAdapter()._build_crew(config, [], "topic")
