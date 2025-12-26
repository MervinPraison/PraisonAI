"""
Unit tests for cloud provider adapters.
"""
from unittest.mock import Mock, patch, MagicMock
import subprocess


def test_base_provider_interface():
    """Test BaseProvider abstract interface."""
    from praisonai.deploy.providers.base import BaseProvider
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    assert hasattr(BaseProvider, 'deploy')
    assert hasattr(BaseProvider, 'doctor')
    assert hasattr(BaseProvider, 'plan')


@patch('subprocess.run')
def test_aws_provider_doctor_success(mock_run):
    """Test AWS provider doctor check success."""
    from praisonai.deploy.providers.aws import AWSProvider
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    config = CloudConfig(
        provider=CloudProvider.AWS,
        region="us-east-1",
        service_name="test-service"
    )
    
    mock_run.return_value = Mock(
        returncode=0,
        stdout='{"UserId": "test", "Account": "123456789012"}'
    )
    
    provider = AWSProvider(config)
    report = provider.doctor()
    
    assert report.total_checks > 0


@patch('subprocess.run')
def test_aws_provider_plan(mock_run):
    """Test AWS provider plan generation."""
    from praisonai.deploy.providers.aws import AWSProvider
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    config = CloudConfig(
        provider=CloudProvider.AWS,
        region="us-east-1",
        service_name="test-service",
        cpu="256",
        memory="512"
    )
    
    provider = AWSProvider(config)
    plan = provider.plan()
    
    assert plan is not None
    assert "service_name" in plan
    assert plan["service_name"] == "test-service"
    assert plan["region"] == "us-east-1"


@patch('subprocess.run')
def test_aws_provider_deploy_success(mock_run):
    """Test AWS provider deploy success."""
    from praisonai.deploy.providers.aws import AWSProvider
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    config = CloudConfig(
        provider=CloudProvider.AWS,
        region="us-east-1",
        service_name="test-service",
        image="test-image:latest"
    )
    
    mock_run.return_value = Mock(
        returncode=0,
        stdout='{"service": {"serviceArn": "arn:aws:ecs:us-east-1:123:service/test"}}'
    )
    
    provider = AWSProvider(config)
    result = provider.deploy()
    
    assert result.success is True


@patch('subprocess.run')
def test_aws_provider_deploy_failure(mock_run):
    """Test AWS provider deploy failure."""
    from praisonai.deploy.providers.aws import AWSProvider
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    config = CloudConfig(
        provider=CloudProvider.AWS,
        region="us-east-1",
        service_name="test-service"
    )
    
    mock_run.side_effect = subprocess.CalledProcessError(1, 'aws')
    
    provider = AWSProvider(config)
    result = provider.deploy()
    
    assert result.success is False
    assert result.error is not None


@patch('subprocess.run')
def test_azure_provider_doctor_success(mock_run):
    """Test Azure provider doctor check success."""
    from praisonai.deploy.providers.azure import AzureProvider
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    config = CloudConfig(
        provider=CloudProvider.AZURE,
        region="eastus",
        service_name="test-service",
        resource_group="test-rg"
    )
    
    mock_run.return_value = Mock(
        returncode=0,
        stdout='{"id": "sub-123", "state": "Enabled"}'
    )
    
    provider = AzureProvider(config)
    report = provider.doctor()
    
    assert report.total_checks > 0


@patch('subprocess.run')
def test_azure_provider_plan(mock_run):
    """Test Azure provider plan generation."""
    from praisonai.deploy.providers.azure import AzureProvider
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    config = CloudConfig(
        provider=CloudProvider.AZURE,
        region="eastus",
        service_name="test-service",
        resource_group="test-rg"
    )
    
    provider = AzureProvider(config)
    plan = provider.plan()
    
    assert plan is not None
    assert "service_name" in plan
    assert plan["resource_group"] == "test-rg"


@patch('subprocess.run')
def test_azure_provider_deploy_success(mock_run):
    """Test Azure provider deploy success."""
    from praisonai.deploy.providers.azure import AzureProvider
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    config = CloudConfig(
        provider=CloudProvider.AZURE,
        region="eastus",
        service_name="test-service",
        resource_group="test-rg",
        image="test-image:latest"
    )
    
    mock_run.return_value = Mock(
        returncode=0,
        stdout='{"properties": {"configuration": {"ingress": {"fqdn": "test.azurecontainerapps.io"}}}}'
    )
    
    provider = AzureProvider(config)
    result = provider.deploy()
    
    assert result.success is True


@patch('subprocess.run')
def test_azure_provider_deploy_failure(mock_run):
    """Test Azure provider deploy failure."""
    from praisonai.deploy.providers.azure import AzureProvider
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    config = CloudConfig(
        provider=CloudProvider.AZURE,
        region="eastus",
        service_name="test-service",
        resource_group="test-rg"
    )
    
    mock_run.side_effect = subprocess.CalledProcessError(1, 'az')
    
    provider = AzureProvider(config)
    result = provider.deploy()
    
    assert result.success is False


@patch('subprocess.run')
def test_gcp_provider_doctor_success(mock_run):
    """Test GCP provider doctor check success."""
    from praisonai.deploy.providers.gcp import GCPProvider
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    config = CloudConfig(
        provider=CloudProvider.GCP,
        region="us-central1",
        service_name="test-service",
        project_id="test-project"
    )
    
    mock_run.return_value = Mock(
        returncode=0,
        stdout="test-project"
    )
    
    provider = GCPProvider(config)
    report = provider.doctor()
    
    assert report.total_checks > 0


@patch('subprocess.run')
def test_gcp_provider_plan(mock_run):
    """Test GCP provider plan generation."""
    from praisonai.deploy.providers.gcp import GCPProvider
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    config = CloudConfig(
        provider=CloudProvider.GCP,
        region="us-central1",
        service_name="test-service",
        project_id="test-project"
    )
    
    provider = GCPProvider(config)
    plan = provider.plan()
    
    assert plan is not None
    assert "service_name" in plan
    assert plan["project_id"] == "test-project"


@patch('subprocess.run')
def test_gcp_provider_deploy_success(mock_run):
    """Test GCP provider deploy success."""
    from praisonai.deploy.providers.gcp import GCPProvider
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    config = CloudConfig(
        provider=CloudProvider.GCP,
        region="us-central1",
        service_name="test-service",
        project_id="test-project",
        image="test-image:latest"
    )
    
    mock_run.return_value = Mock(
        returncode=0,
        stdout='{"status": {"url": "https://test-service-abc123.run.app"}}'
    )
    
    provider = GCPProvider(config)
    result = provider.deploy()
    
    assert result.success is True
    assert "run.app" in result.url


@patch('subprocess.run')
def test_gcp_provider_deploy_failure(mock_run):
    """Test GCP provider deploy failure."""
    from praisonai.deploy.providers.gcp import GCPProvider
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    config = CloudConfig(
        provider=CloudProvider.GCP,
        region="us-central1",
        service_name="test-service",
        project_id="test-project"
    )
    
    mock_run.side_effect = subprocess.CalledProcessError(1, 'gcloud')
    
    provider = GCPProvider(config)
    result = provider.deploy()
    
    assert result.success is False


def test_get_provider_aws():
    """Test getting AWS provider."""
    from praisonai.deploy.providers import get_provider
    from praisonai.deploy.providers.aws import AWSProvider
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    config = CloudConfig(
        provider=CloudProvider.AWS,
        region="us-east-1",
        service_name="test"
    )
    
    provider = get_provider(config)
    assert isinstance(provider, AWSProvider)


def test_get_provider_azure():
    """Test getting Azure provider."""
    from praisonai.deploy.providers import get_provider
    from praisonai.deploy.providers.azure import AzureProvider
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    config = CloudConfig(
        provider=CloudProvider.AZURE,
        region="eastus",
        service_name="test",
        resource_group="test-rg"
    )
    
    provider = get_provider(config)
    assert isinstance(provider, AzureProvider)


def test_get_provider_gcp():
    """Test getting GCP provider."""
    from praisonai.deploy.providers import get_provider
    from praisonai.deploy.providers.gcp import GCPProvider
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    config = CloudConfig(
        provider=CloudProvider.GCP,
        region="us-central1",
        service_name="test",
        project_id="test-project"
    )
    
    provider = get_provider(config)
    assert isinstance(provider, GCPProvider)
