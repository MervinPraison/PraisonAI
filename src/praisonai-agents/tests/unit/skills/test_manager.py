"""Tests for Agent Skills manager."""

from pathlib import Path
import tempfile


class TestSkillManager:
    """Tests for SkillManager class."""
    
    def test_init_empty(self):
        """Test initializing empty manager."""
        from praisonaiagents.skills.manager import SkillManager
        
        manager = SkillManager()
        
        assert len(manager) == 0
        assert manager.skill_names == []
    
    def test_discover_skills(self):
        """Test discovering skills from directory."""
        from praisonaiagents.skills.manager import SkillManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a skill
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---
""")
            
            manager = SkillManager()
            count = manager.discover([tmpdir], include_defaults=False)
            
            assert count == 1
            assert len(manager) == 1
            assert "test-skill" in manager
    
    def test_add_skill(self):
        """Test adding a single skill."""
        from praisonaiagents.skills.manager import SkillManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "my-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: my-skill
description: My skill
---
""")
            
            manager = SkillManager()
            skill = manager.add_skill(str(skill_dir))
            
            assert skill is not None
            assert skill.properties.name == "my-skill"
            assert "my-skill" in manager
    
    def test_get_skill(self):
        """Test getting a skill by name."""
        from praisonaiagents.skills.manager import SkillManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---
""")
            
            manager = SkillManager()
            manager.add_skill(str(skill_dir))
            
            skill = manager.get_skill("test-skill")
            
            assert skill is not None
            assert skill.properties.name == "test-skill"
    
    def test_get_skill_not_found(self):
        """Test getting nonexistent skill."""
        from praisonaiagents.skills.manager import SkillManager
        
        manager = SkillManager()
        skill = manager.get_skill("nonexistent")
        
        assert skill is None
    
    def test_activate_by_name(self):
        """Test activating skill by name."""
        from praisonaiagents.skills.manager import SkillManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---

# Instructions
""")
            
            manager = SkillManager()
            manager.add_skill(str(skill_dir))
            
            result = manager.activate_by_name("test-skill")
            
            assert result is True
            skill = manager.get_skill("test-skill")
            assert skill.is_activated
    
    def test_get_available_skills(self):
        """Test getting available skills metadata."""
        from praisonaiagents.skills.manager import SkillManager
        from praisonaiagents.skills.models import SkillMetadata
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---
""")
            
            manager = SkillManager()
            manager.add_skill(str(skill_dir))
            
            skills = manager.get_available_skills()
            
            assert len(skills) == 1
            assert isinstance(skills[0], SkillMetadata)
            assert skills[0].name == "test-skill"
    
    def test_fallback_skill_hidden_when_capability_present(self):
        """A fallback skill is hidden when its target tool is available."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "web-via-terminal"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: web-via-terminal
description: Fetch the web via terminal when no web tool is available.
fallback_for_tools: [web_search]
---
""")

            manager = SkillManager()
            manager.add_skill(str(skill_dir))
            # Target tool present -> fallback should be hidden.
            manager._validator._tool_cache = {"web_search"}

            names = [s.name for s in manager.get_available_skills()]
            assert "web-via-terminal" not in names

    def test_fallback_skill_offered_when_capability_absent(self):
        """A fallback skill is offered when its target tool is absent."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "web-via-terminal"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: web-via-terminal
description: Fetch the web via terminal when no web tool is available.
fallback_for_tools: [web_search]
---
""")

            manager = SkillManager()
            manager.add_skill(str(skill_dir))
            # Target tool absent -> fallback should be offered.
            manager._validator._tool_cache = {"terminal"}

            names = [s.name for s in manager.get_available_skills()]
            assert "web-via-terminal" in names

    def test_fallback_skill_hidden_when_own_requirements_unmet(self):
        """A fallback skill is hidden when its own requires_* gate is unmet.

        Even in the default (non-strict) enforcement mode, a fallback skill
        that needs a tool which is absent must not be offered — otherwise an
        unusable skill leaks into the prompt.
        """
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "web-via-terminal"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: web-via-terminal
description: Fetch the web via terminal when no web tool is available.
requires_tools: [terminal]
fallback_for_tools: [web_search]
---
""")

            manager = SkillManager()
            manager.add_skill(str(skill_dir))
            # Fallback target absent (good) but required terminal also absent.
            manager._validator._tool_cache = set()

            names = [s.name for s in manager.get_available_skills()]
            assert "web-via-terminal" not in names

    def test_fallback_skill_offered_when_own_requirements_met(self):
        """A fallback skill is offered when its requires_* gate is satisfied."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "web-via-terminal"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: web-via-terminal
description: Fetch the web via terminal when no web tool is available.
requires_tools: [terminal]
fallback_for_tools: [web_search]
---
""")

            manager = SkillManager()
            manager.add_skill(str(skill_dir))
            # Required terminal present, fallback target absent -> offered.
            manager._validator._tool_cache = {"terminal"}

            names = [s.name for s in manager.get_available_skills()]
            assert "web-via-terminal" in names

    def test_to_prompt(self):
        """Test generating prompt XML."""
        from praisonaiagents.skills.manager import SkillManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---
""")
            
            manager = SkillManager()
            manager.add_skill(str(skill_dir))
            
            prompt = manager.to_prompt()
            
            assert "<available_skills>" in prompt
            assert "test-skill" in prompt
            assert "A test skill" in prompt
    
    def test_get_instructions(self):
        """Test getting instructions for a skill."""
        from praisonaiagents.skills.manager import SkillManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---

# Instructions

Do this and that.
""")
            
            manager = SkillManager()
            manager.add_skill(str(skill_dir))
            
            instructions = manager.get_instructions("test-skill")
            
            assert instructions is not None
            assert "Do this and that" in instructions
    
    def test_load_resources(self):
        """Test loading resources for a skill."""
        from praisonaiagents.skills.manager import SkillManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---
""")
            
            # Create scripts directory
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir()
            (scripts_dir / "helper.py").write_text("print('hello')")
            
            manager = SkillManager()
            manager.add_skill(str(skill_dir))
            
            result = manager.load_resources("test-skill")
            
            assert result is True
            skill = manager.get_skill("test-skill")
            assert skill.resources_loaded
    
    def test_clear(self):
        """Test clearing all skills."""
        from praisonaiagents.skills.manager import SkillManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---
""")
            
            manager = SkillManager()
            manager.add_skill(str(skill_dir))
            assert len(manager) == 1
            
            manager.clear()
            
            assert len(manager) == 0
    
    def test_iteration(self):
        """Test iterating over skills."""
        from praisonaiagents.skills.manager import SkillManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two skills
            for name in ["skill-a", "skill-b"]:
                skill_dir = Path(tmpdir) / name
                skill_dir.mkdir()
                (skill_dir / "SKILL.md").write_text(f"""---
name: {name}
description: Skill {name}
---
""")
            
            manager = SkillManager()
            manager.discover([tmpdir], include_defaults=False)
            
            names = [s.properties.name for s in manager]
            
            assert len(names) == 2
            assert "skill-a" in names
            assert "skill-b" in names

    def test_patch_skill_rejects_path_traversal(self):
        """Patch operation should reject traversal paths."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "safe-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: safe-skill
description: safe
---
content
""")

            manager = SkillManager()
            manager.add_skill(str(skill_dir))

            result = manager.patch_skill("safe-skill", "content", "updated", "../outside.md", propose=False)
            assert result["success"] is False
            assert "Path traversal detected" in result["error"]

    def test_write_skill_file_rejects_path_traversal(self):
        """Write operation should reject traversal paths."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "safe-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: safe-skill
description: safe
---
content
""")

            manager = SkillManager()
            manager.add_skill(str(skill_dir))

            result = manager.write_skill_file("safe-skill", "scripts/../../outside.py", "print('x')", propose=False)
            assert result["success"] is False
            assert "Path traversal detected" in result["error"]


class TestSkillApprovalGate:
    """Tests for the safe-by-default skill mutation approval gate."""

    def test_create_stages_by_default(self, monkeypatch):
        """create_skill defaults to staging, not writing to disk."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("PRAISONAI_HOME", str(Path(tmpdir) / "home"))
            from praisonaiagents import paths
            paths._clear_cache()

            manager = SkillManager()
            result = manager.create_skill("staged-skill", "# body")

            assert result["status"] == "pending"
            assert result["id"].startswith("skl-")
            # Not written to disk / not loaded live.
            assert "staged-skill" not in manager
            skill_path = Path(tmpdir) / "home" / "skills" / "staged-skill"
            assert not skill_path.exists()

    def test_propose_false_writes_directly(self, monkeypatch):
        """propose=False bypasses the gate and writes immediately."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("PRAISONAI_HOME", str(Path(tmpdir) / "home"))
            from praisonaiagents import paths
            paths._clear_cache()

            manager = SkillManager()
            result = manager.create_skill("direct-skill", "# body", propose=False)

            assert result["success"] is True
            assert result.get("status") != "pending"
            assert "direct-skill" in manager

    def test_write_prefers_project_dir_when_present(self, monkeypatch):
        """Writes land in project ./.praisonai/skills/ when that dir exists."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("PRAISONAI_HOME", str(Path(tmpdir) / "home"))
            from praisonaiagents import paths
            paths._clear_cache()

            project_skills = Path(tmpdir) / ".praisonai" / "skills"
            project_skills.mkdir(parents=True)

            manager = SkillManager()
            result = manager.create_skill("proj-skill", "# body", propose=False)

            assert result["success"] is True
            assert (project_skills / "proj-skill" / "SKILL.md").exists()
            home_skill = Path(tmpdir) / "home" / "skills" / "proj-skill"
            assert not home_skill.exists()

    def test_write_falls_back_to_home_without_project_dir(self, monkeypatch):
        """Without a project skills dir, writes go to the user home dir."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("PRAISONAI_HOME", str(Path(tmpdir) / "home"))
            from praisonaiagents import paths
            paths._clear_cache()

            manager = SkillManager()
            result = manager.create_skill("home-skill", "# body", propose=False)

            assert result["success"] is True
            home_skill = Path(tmpdir) / "home" / "skills" / "home-skill" / "SKILL.md"
            assert home_skill.exists()

    def test_env_disables_approval(self, monkeypatch):
        """SKILL_WRITE_APPROVAL=0 makes writes direct by default."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("PRAISONAI_HOME", str(Path(tmpdir) / "home"))
            monkeypatch.setenv("SKILL_WRITE_APPROVAL", "0")
            from praisonaiagents import paths
            paths._clear_cache()

            manager = SkillManager()
            result = manager.create_skill("env-skill", "# body")

            assert result.get("status") != "pending"
            assert "env-skill" in manager

    def test_list_pending_and_approve(self, monkeypatch):
        """Staged mutation appears in list_pending and applies on approve."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("PRAISONAI_HOME", str(Path(tmpdir) / "home"))
            from praisonaiagents import paths
            paths._clear_cache()

            manager = SkillManager()
            staged = manager.create_skill("approve-me", "# body")
            request_id = staged["id"]

            pending = manager.list_pending()
            assert any(p["id"] == request_id for p in pending)
            assert pending[0]["action"] == "create"

            result = manager.approve(request_id)
            assert result["success"] is True
            assert "approve-me" in manager
            # Pending entry consumed.
            assert manager.list_pending() == []

    def test_reject_discards_mutation(self, monkeypatch):
        """Rejecting a staged mutation never writes it."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("PRAISONAI_HOME", str(Path(tmpdir) / "home"))
            from praisonaiagents import paths
            paths._clear_cache()

            manager = SkillManager()
            staged = manager.create_skill("reject-me", "# body")
            request_id = staged["id"]

            result = manager.reject(request_id)
            assert result["success"] is True
            assert result["status"] == "rejected"
            assert "reject-me" not in manager
            assert manager.list_pending() == []

    def test_approve_unknown_id_fails(self, monkeypatch):
        """Approving a non-existent id returns an error."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("PRAISONAI_HOME", str(Path(tmpdir) / "home"))
            from praisonaiagents import paths
            paths._clear_cache()

            manager = SkillManager()
            result = manager.approve("skl-nonexistent")
            assert result["success"] is False

    def test_stage_rejects_oversized_content(self, monkeypatch):
        """Oversized proposals are rejected before reaching the pending store."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("PRAISONAI_HOME", str(Path(tmpdir) / "home"))
            from praisonaiagents import paths
            paths._clear_cache()

            manager = SkillManager()
            result = manager.create_skill("too-big", "x" * 100_001)

            assert result["success"] is False
            assert manager.list_pending() == []

    def test_stage_rejects_invalid_name(self, monkeypatch):
        """Invalid skill names are rejected at staging time for all actions."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("PRAISONAI_HOME", str(Path(tmpdir) / "home"))
            from praisonaiagents import paths
            paths._clear_cache()

            manager = SkillManager()
            result = manager.edit_skill("../escape", "# body")

            assert result["success"] is False
            assert manager.list_pending() == []

    def test_pending_store_size_cap(self, monkeypatch):
        """The pending store refuses new proposals past SKILL_MAX_PENDING."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("PRAISONAI_HOME", str(Path(tmpdir) / "home"))
            monkeypatch.setenv("SKILL_MAX_PENDING", "2")
            from praisonaiagents import paths
            paths._clear_cache()

            manager = SkillManager()
            assert manager.create_skill("one", "# a")["status"] == "pending"
            assert manager.create_skill("two", "# b")["status"] == "pending"
            full = manager.create_skill("three", "# c")
            assert full["success"] is False
            assert len(manager.list_pending()) == 2

    def test_approve_failure_keeps_record(self, monkeypatch):
        """A failed apply preserves the pending record and does not lie in audit."""
        from praisonaiagents.skills.manager import SkillManager

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("PRAISONAI_HOME", str(Path(tmpdir) / "home"))
            from praisonaiagents import paths
            paths._clear_cache()

            manager = SkillManager()
            staged = manager.create_skill("flaky", "# body")
            request_id = staged["id"]

            def _boom(_record):
                return {"success": False, "error": "boom"}

            monkeypatch.setattr(manager, "_apply_pending", _boom)
            result = manager.approve(request_id)

            assert result["success"] is False
            # Record retained for retry.
            assert any(p["id"] == request_id for p in manager.list_pending())

    def test_protocol_conformance(self):
        """SkillManager conforms to SkillMutatorProtocol."""
        from praisonaiagents.skills.manager import SkillManager
        from praisonaiagents.skills.protocols import SkillMutatorProtocol

        assert isinstance(SkillManager(), SkillMutatorProtocol)
