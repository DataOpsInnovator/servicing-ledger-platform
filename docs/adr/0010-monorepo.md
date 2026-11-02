# ADR-0010: Monorepo for the solo portfolio

- **Status:** Accepted.
- **Context:** One engineer needs a reproducible public artifact where application, platform policy, diagrams, and runbooks change together.
- **Decision:** Keep application, Helm, Terraform design, CI templates, ADRs, and operations docs in one repository with clear ownership folders.
- **Alternatives:** Separate application/platform repositories; multiple service repos; generated template repo plus service repo.
- **Rationale:** Atomic review and low initial coordination overhead outweigh independent release cadence for this small project.
- **Consequences:** CI path filtering and ownership boundaries matter; release and environment promotion remain versioned. The monorepo is not permission isolation.
- **Security / operations:** Separate deployment roles and codeowners for sensitive paths; never store secrets in any repository directory.
- **Cost:** No direct infrastructure cost; CI minutes may grow with repository size.
- **Revisit when:** Multiple teams need independent access, release cadence, or ownership and the boundaries are mature enough to split cleanly.

