"""
Tests for the unified branding module.

This module provides the single source of truth for logo/version/branding
across all interactive UIs.
"""

import pytest


class TestBrandingConstants:
    """Tests for branding constants."""
    
    def test_product_name(self):
        """Test PRODUCT_NAME constant."""
        from praisonai.cli.branding import PRODUCT_NAME
        assert PRODUCT_NAME == "Praison AI"
    
    def test_logo_large_exists(self):
        """Test LOGO_LARGE constant exists and has ASCII art."""
        from praisonai.cli.branding import LOGO_LARGE
        assert len(LOGO_LARGE) > 0
        assert "██" in LOGO_LARGE
    
    def test_logo_medium_exists(self):
        """Test LOGO_MEDIUM constant exists."""
        from praisonai.cli.branding import LOGO_MEDIUM
        assert len(LOGO_MEDIUM) > 0
    
    def test_logo_small_exists(self):
        """Test LOGO_SMALL constant exists and has branding."""
        from praisonai.cli.branding import LOGO_SMALL
        assert len(LOGO_SMALL) > 0
        assert "Praison AI" in LOGO_SMALL
    
    def test_logo_minimal_exists(self):
        """Test LOGO_MINIMAL constant exists and has branding."""
        from praisonai.cli.branding import LOGO_MINIMAL
        assert LOGO_MINIMAL == "Praison AI"


class TestGetLogo:
    """Tests for get_logo function."""
    
    def test_get_logo_wide_terminal(self):
        """Test get_logo returns LOGO_LARGE for wide terminals."""
        from praisonai.cli.branding import get_logo, LOGO_LARGE
        assert get_logo(100) == LOGO_LARGE
        assert get_logo(80) == LOGO_LARGE
        assert get_logo(75) == LOGO_LARGE
    
    def test_get_logo_medium_terminal(self):
        """Test get_logo returns LOGO_MEDIUM for medium terminals."""
        from praisonai.cli.branding import get_logo, LOGO_MEDIUM
        assert get_logo(74) == LOGO_MEDIUM
        assert get_logo(50) == LOGO_MEDIUM
        assert get_logo(40) == LOGO_MEDIUM
    
    def test_get_logo_narrow_terminal(self):
        """Test get_logo returns LOGO_SMALL for narrow terminals."""
        from praisonai.cli.branding import get_logo, LOGO_SMALL
        assert get_logo(39) == LOGO_SMALL
        assert get_logo(30) == LOGO_SMALL
        assert get_logo(20) == LOGO_SMALL


class TestGetVersion:
    """Tests for get_version function."""
    
    def test_get_version_returns_string(self):
        """Test get_version returns a string."""
        from praisonai.cli.branding import get_version
        version = get_version()
        assert isinstance(version, str)
        assert len(version) > 0
    
    def test_get_version_format(self):
        """Test get_version returns a valid version format."""
        from praisonai.cli.branding import get_version
        version = get_version()
        # Should be in format X.Y.Z or similar
        parts = version.split(".")
        assert len(parts) >= 2


class TestGetBanner:
    """Tests for get_banner function."""
    
    def test_get_banner_includes_logo(self):
        """Test get_banner includes logo."""
        from praisonai.cli.branding import get_banner
        banner = get_banner(100)
        assert "██" in banner or "Praison" in banner
    
    def test_get_banner_includes_version(self):
        """Test get_banner includes version when requested."""
        from praisonai.cli.branding import get_banner, get_version
        banner = get_banner(100, show_version=True)
        version = get_version()
        assert version in banner
    
    def test_get_banner_includes_model(self):
        """Test get_banner includes model when provided."""
        from praisonai.cli.branding import get_banner
        banner = get_banner(100, model="gpt-4o")
        assert "gpt-4o" in banner


class TestGetWelcomeTips:
    """Tests for get_welcome_tips function."""
    
    def test_get_welcome_tips_content(self):
        """Test get_welcome_tips returns helpful tips."""
        from praisonai.cli.branding import get_welcome_tips
        tips = get_welcome_tips()
        assert "Enter" in tips or "help" in tips
        assert len(tips) > 0
