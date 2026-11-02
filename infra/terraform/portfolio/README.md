# Terraform implementation boundary

This folder records the intended Terraform layout; it intentionally contains no `apply`-ready AWS environment in this initial scaffold. The local simulator and documents can be used without an AWS account. Do not copy placeholder values into a real account.

## Planned roots and modules

```text
infra/terraform/
  bootstrap/                 One-time encrypted state bucket and access policy
  modules/
    network/                 VPC, subnet tiers, routes, endpoints, security groups
    eks/                     EKS control plane, managed node group, access entries
    data/                    RDS PostgreSQL subnet group, KMS, backup policy
    messaging/               SQS queue, DLQ, encryption, redrive policy
    guardrails/               Budget, tags, CloudTrail/Config baseline
  environments/
    portfolio/               One-region, low-cost, short-lived composition
    reference/                Documentation only; never deployed continuously
```

## State, change, and access rules

- Create a dedicated state bucket in a separate bootstrap step; enable versioning, block public access, server-side encryption, and narrowly scoped access.
- Use an S3 backend with native lock files (`use_lockfile = true`) on Terraform versions that support it; pin the CLI and provider versions. The [official S3 backend guide](https://developer.hashicorp.com/terraform/language/backend/s3) documents this setting and recommends bucket versioning for state recovery. Never commit state, plan files, credentials, or `.tfvars` containing secrets.
- Use separate state keys for each environment and narrowly scoped deployment roles. CI assumes roles through short-lived OIDC credentials; no long-lived AWS keys in repository secrets.
- Review a saved plan, policy/security scan results, and cost delta before an authorized apply. A human approves any privileged, destructive, or production-equivalent change.
- Keep the state bucket and its recovery path outside the stack it controls. Restrict state reads because state can contain sensitive values even when outputs are marked sensitive.
- Record imports and state migrations in reviewed changes; do not hand-edit state. Drift detection is a scheduled plan with notification, not an automatic apply.

## Provider and example shape

Each root pins a tested AWS provider range and declares the provider region explicitly. Module inputs use typed variables, validation, explicit tags, and narrow outputs. Shared modules are versioned; environment roots own composition and state.

Representative guardrail pseudocode:

```hcl
terraform {
  required_version = ">= 1.10, < 2.0"
  backend "s3" {
    bucket       = "<separately-created-state-bucket>"
    key          = "portfolio/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region
  default_tags { tags = {
    Project     = "servicing-ledger-platform"
    Environment = "portfolio"
    ManagedBy   = "terraform"
    DataClass   = "synthetic-only"
  } }
}
```

The bucket name and provider versions are placeholders until a real account, region, and version matrix are selected. Budget alarms are notifications, not spending caps; the deployment workflow must also gate resource creation and require teardown evidence.

## Validation to add before deployment

Format and validate all roots; run module unit/policy checks and static security scans; inspect the plan for public ingress, broad IAM, unencrypted storage, missing tags, and unbounded resources; then have a human review it. These are planned project tasks. No Terraform plan or apply has been run for this scaffold.

