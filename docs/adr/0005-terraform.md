# ADR-0005: Terraform owns AWS infrastructure

- **Status:** Accepted.
- **Context:** The platform needs repeatable and reviewable AWS resources with isolated environment state.
- **Decision:** Terraform owns AWS accounts' VPC, EKS, RDS, SQS, IAM, KMS, backup, and budget resources. Helm/Argo CD own Kubernetes desired state.
- **Alternatives:** AWS CDK/CloudFormation; split ownership by service; Crossplane.
- **Rationale:** The candidate profile includes Terraform, and a single IaC owner makes plan review, state access, and drift boundaries clear.
- **Consequences:** State bootstrap, provider/module pinning, migration, imports, and plan workflows require care. Never manage one resource in both Terraform and CDK.
- **Security / operations:** Encrypted/versioned remote state, lock file, least-privilege OIDC role, separate plan/apply, no automatic destructive apply.
- **Cost:** Terraform itself does not add infrastructure cost; its state bucket and tooling do.
- **Revisit when:** A concrete team or resource need makes another owner demonstrably safer; define a migration boundary first.

