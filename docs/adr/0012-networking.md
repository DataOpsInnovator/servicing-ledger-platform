# ADR-0012: Isolated VPC before centralized networking

- **Status:** Accepted for portfolio.
- **Context:** A solo portfolio deployment needs clear trust boundaries, but Transit Gateway, central egress, and an organization landing zone would dominate the implementation and recurring cost.
- **Decision:** Use one isolated VPC with public ingress, private application subnets, and isolated data subnets. Keep the API endpoint restricted and document centralized egress as enterprise-only.
- **Alternatives:** Shared networking account with Transit Gateway; public-only subnets; one NAT per AZ; private endpoints without NAT.
- **Rationale:** The VPC demonstrates segmentation without pretending to be a multi-account institution network. A short-lived lab may accept one NAT's AZ dependency; high-availability reference uses per-AZ egress or evaluated endpoints.
- **Consequences:** Cross-account routing, shared inspection, and enterprise DNS are not implemented. CIDRs must be checked against corporate/VPN ranges before use.
- **Security / operations:** No public database, restricted EKS API CIDRs, workload egress allowlist, narrow security groups, and validated NetworkPolicy enforcement.
- **Cost:** One NAT and selected endpoints control the lab baseline; per-AZ NAT and Transit Gateway add steady fees.
- **Revisit when:** Multiple accounts or central network policy become actual requirements.

