# ADR-0006: Managed node groups first; defer Karpenter

- **Status:** Accepted for first cloud iteration.
- **Context:** Karpenter can improve dynamic capacity but adds controller, permissions, disruption policies, and debugging to a small workload.
- **Decision:** Begin with one bounded managed node group; add Karpenter only after demand and node-waste evidence exist.
- **Alternatives:** Karpenter from day one; Cluster Autoscaler; Fargate; fixed EC2.
- **Rationale:** A small predictable workload benefits from operational simplicity. If Karpenter is adopted, do not run Cluster Autoscaler for the same node pools without explicit ownership.
- **Consequences:** Less elastic capacity and possible idle node cost; define max size and nonproduction schedule.
- **Security / operations:** Restrict node IAM, use approved AMIs, enforce workload resource requests, and test node disruption.
- **Cost:** Fixed capacity can waste money; Karpenter savings are not assumed until measured.
- **Revisit when:** Observed pending pods, utilization, or workload variation justify dynamic provisioning.

