# ADR-0011: Defer service mesh

- **Status:** Accepted to defer.
- **Context:** The first workflow has one API and one consumer; mutual TLS and traffic routing are already handled at service boundaries and AWS TLS endpoints.
- **Decision:** Do not deploy a service mesh in the portfolio MVP.
- **Alternatives:** Istio, Linkerd, App Mesh, or application-level mTLS and OpenTelemetry.
- **Rationale:** A mesh adds control-plane upgrades, sidecar/resource cost, policy debugging, and another failure mode without a demonstrated need.
- **Consequences:** Service identity and telemetry use workload IAM, Kubernetes policy, TLS to managed services, and OTel instrumentation. Advanced east-west controls remain less comprehensive.
- **Security / operations:** Revisit if internal mTLS, identity-aware authorization, or traffic shaping cannot be satisfied with simpler controls.
- **Cost:** Avoids persistent control-plane and sidecar overhead; exact savings are not measured.
- **Revisit when:** Multiple services or a verified security/traffic requirement appears.

