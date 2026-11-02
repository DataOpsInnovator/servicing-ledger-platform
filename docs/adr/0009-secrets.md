# ADR-0009: Secrets Manager over self-hosted Vault

- **Status:** Accepted for AWS reference.
- **Context:** The AWS runtime needs database credentials and possibly signing material; operating Vault would add an unnecessary control plane for this one service.
- **Decision:** Use AWS Secrets Manager for runtime secrets and KMS for encryption; workload identity grants access only to required secret ARNs.
- **Alternatives:** HashiCorp Vault; Kubernetes Secrets only; environment-file secrets.
- **Rationale:** Managed secret lifecycle and AWS identity integration fit the one-region reference without introducing a separate secret service to operate.
- **Consequences:** AWS dependency and service cost; rotation can disrupt connections if not rehearsed. Kubernetes Secrets are not the source of truth for credentials.
- **Security / operations:** No credentials in Git, image, logs, or prompts; rotate with backward-compatible application behavior and audit secret access.
- **Cost:** Per-secret and API charges; avoid duplicating secrets across environments without need.
- **Revisit when:** Multi-cloud/hybrid or policy requirements justify Vault and its availability, upgrade, and recovery burden.

