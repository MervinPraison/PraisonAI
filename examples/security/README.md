# Security Features Example

This example demonstrates PraisonAI security features including SBOM generation, lockfile validation, dependency auditing, and PII redaction.

## Features Demonstrated

- **SBOM Generation**: Generate Software Bill of Materials in CycloneDX or SPDX format
- **Lockfile Validation**: Validate presence and format of dependency lockfiles
- **Dependency Auditing**: Audit dependencies for vulnerabilities
- **PII Redaction**: Detect and redact personally identifiable information

## Quick Start

```bash
python security_example.py
```

## CLI Commands

### SBOM Generation

```bash
# Generate CycloneDX SBOM
praisonai recipe sbom ./my-recipe --format cyclonedx -o sbom.json

# Generate SPDX SBOM
praisonai recipe sbom ./my-recipe --format spdx -o sbom.json
```

### Dependency Auditing

```bash
# Audit dependencies
praisonai recipe audit ./my-recipe

# Strict audit (fail on issues)
praisonai recipe audit ./my-recipe --strict
```

### Lockfile Validation

```bash
# Validate recipe (includes lockfile check)
praisonai recipe validate ./my-recipe --require-lockfile
```

## PII Redaction Configuration

In your `TEMPLATE.yaml`:

```yaml
data_policy:
  pii:
    mode: redact  # allow, deny, or redact
    fields:
      - email
      - phone
      - ssn
      - credit_card
```
