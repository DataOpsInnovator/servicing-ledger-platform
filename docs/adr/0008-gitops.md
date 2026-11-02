# ADR-0008: GitOps with staged rollout

- **Status:** Accepted for advanced tier.
- **Context:** Infrastructure and workload changes need review, reproducibility, and drift visibility.
- **Decision:** GitHub Actions validates/builds; Argo CD reconciles reviewed environment manifests. Progressive delivery is staged and uses business correctness signals where supported.
- **Alternatives:** CI pushes directly with `kubectl`; Argo Rollouts/canary; blue/green; manual console changes.
- **Rationale:** Separating build from deploy narrows credentials and makes desired state reviewable. A failed rollout must pause and roll back through a defined path.
- **Consequences:** Argo CD becomes an operational dependency for delivery; it does not stop already-running business traffic if unavailable.
- **Security / operations:** Use OIDC, protected branches, pinned actions, immutable image digests, scoped sync roles, audit history, and human approval for sensitive changes.
- **Cost:** Argo CD has little direct cost but consumes cluster resources; avoid a second control plane in the minimum tier.
- **Revisit when:** Deployment scale or team topology favors another controller; preserve the identity and approval guarantees.

