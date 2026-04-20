"""
Tests for G-D: SkillPromptBudget functionality.
"""

import pytest
from praisonaiagents.skills.budget import SkillPromptBudget, apply_budget
from praisonaiagents.skills.models import SkillMetadata


def create_test_skill(name: str, description: str) -> SkillMetadata:
    """Helper to create test skill metadata."""
    return SkillMetadata(
        name=name,
        description=description,
        location=f"./skills/{name}"
    )


def test_skill_prompt_budget_defaults():
    """Test SkillPromptBudget default values."""
    budget = SkillPromptBudget()
    assert budget.max_chars == 4096
    assert budget.max_skills == 50
    assert budget.strategy == "fifo"


def test_apply_budget_no_skills():
    """Test budget application with empty skill list."""
    budget = SkillPromptBudget(max_chars=1000, max_skills=10)
    skills, was_truncated = apply_budget([], budget)
    assert skills == []
    assert was_truncated is False


def test_apply_budget_under_limits():
    """Test budget application when skills are under limits."""
    skills = [
        create_test_skill("skill1", "Short description"),
        create_test_skill("skill2", "Another short description"),
    ]
    budget = SkillPromptBudget(max_chars=1000, max_skills=10)
    
    filtered_skills, was_truncated = apply_budget(skills, budget)
    assert len(filtered_skills) == 2
    assert was_truncated is False
    assert filtered_skills[0].name == "skill1"
    assert filtered_skills[1].name == "skill2"


def test_apply_budget_skill_count_limit():
    """Test budget application when skill count exceeds limit."""
    skills = [
        create_test_skill(f"skill{i}", "Description") 
        for i in range(1, 6)  # 5 skills
    ]
    budget = SkillPromptBudget(max_chars=10000, max_skills=3)
    
    filtered_skills, was_truncated = apply_budget(skills, budget)
    assert len(filtered_skills) == 3
    assert was_truncated is True
    # Should keep first 3 skills
    assert filtered_skills[0].name == "skill1"
    assert filtered_skills[2].name == "skill3"


def test_apply_budget_char_limit():
    """Test budget application when character count exceeds limit."""
    skills = [
        create_test_skill("skill1", "A" * 100),  # ~150 chars with XML
        create_test_skill("skill2", "B" * 100),  # ~150 chars with XML  
        create_test_skill("skill3", "C" * 100),  # ~150 chars with XML
    ]
    budget = SkillPromptBudget(max_chars=250, max_skills=10)  # Only fits ~1.5 skills
    
    filtered_skills, was_truncated = apply_budget(skills, budget)
    assert len(filtered_skills) == 1  # Only first skill fits
    assert was_truncated is True
    assert filtered_skills[0].name == "skill1"


def test_apply_budget_alpha_strategy():
    """Test alphabetical sorting strategy."""
    skills = [
        create_test_skill("zebra", "Description"),
        create_test_skill("apple", "Description"),
        create_test_skill("banana", "Description"),
    ]
    budget = SkillPromptBudget(max_chars=10000, max_skills=10, strategy="alpha")
    
    filtered_skills, was_truncated = apply_budget(skills, budget)
    assert len(filtered_skills) == 3
    assert was_truncated is False
    # Should be alphabetically sorted
    assert filtered_skills[0].name == "apple"
    assert filtered_skills[1].name == "banana" 
    assert filtered_skills[2].name == "zebra"


def test_apply_budget_fifo_strategy():
    """Test FIFO (first-in-first-out) strategy."""
    skills = [
        create_test_skill("first", "Description"),
        create_test_skill("second", "Description"),
        create_test_skill("third", "Description"),
    ]
    budget = SkillPromptBudget(max_chars=10000, max_skills=10, strategy="fifo")
    
    filtered_skills, was_truncated = apply_budget(skills, budget)
    assert len(filtered_skills) == 3
    assert was_truncated is False
    # Should maintain original order
    assert filtered_skills[0].name == "first"
    assert filtered_skills[1].name == "second"
    assert filtered_skills[2].name == "third"


def test_apply_budget_both_limits():
    """Test budget when both skill count and char limits are hit."""
    skills = [
        create_test_skill(f"skill{i}", "A" * 50) 
        for i in range(1, 11)  # 10 skills
    ]
    budget = SkillPromptBudget(max_chars=200, max_skills=3)
    
    filtered_skills, was_truncated = apply_budget(skills, budget)
    # Should be limited by character count (fewer than max_skills)
    assert len(filtered_skills) <= 3
    assert was_truncated is True