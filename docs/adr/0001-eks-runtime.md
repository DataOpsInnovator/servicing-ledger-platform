# ADR-0001: EKS as the reference runtime

- **Status:** Accepted for the portfolio reference; local implementation remains runtime-neutral.
- **Context:** The project should demonstrate a reusable platform path and fits the stated candidate Kubernetes experience, but one API alone does not require Kubernetes.
- **Decision:** Use Amazon EKS in the advanced AWS reference. Keep local demo independent of EKS.
- **Alternatives:** ECS/Fargate for lower operations; EC2 for lowest abstraction; EKS Auto Mode for managed operations.
- **Rationale:** EKS enables demonstrating namespace policy, workload identity, autoscaling, Helm, GitOps, and platform templates in one coherent path.
- **Consequences:** More control-plane, upgrade, add-on, networking, and incident burden than ECS. Start with managed node groups and a short-lived cluster.
- **Security / operations:** Private worker/data paths, scoped cluster access, Pod Identity/IRSA, admission guardrails, and tested upgrades are required.
- **Cost:** Cluster fee and node/network costs continue while the environment runs; scheduled teardown is mandatory.
- **Revisit when:** The project no longer needs Kubernetes platform evidence or ECS can meet the demonstration objectives more simply.

