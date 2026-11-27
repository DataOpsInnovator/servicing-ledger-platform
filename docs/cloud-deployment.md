# AWS staging deployment — operator guide

**Status: deployment configuration written, not executed in AWS.** Use an isolated synthetic-data sandbox account with approved budget. EKS control plane, two NAT gateways, managed nodes, Multi-AZ RDS, ECR, CloudWatch, S3 retention and backups incur charges. RDS deletion protection and S3 COMPLIANCE Object Lock intentionally obstruct teardown; retained objects cannot be deleted during retention. Do not run `apply` until cost/retention approval. No public Kubernetes API or internet ingress by default.

## 0. Prerequisites and release gates

- AWS account and approved infrastructure/admin roles, budget alarm and network access via VPN/SSM-approved VPC runner; AWS CLI, Terraform >=1.10, kubectl, Helm, Docker, Python 3.12/3.13, Cosign and GitHub repository.
- GitHub `Ledger verification` CI must be green. It includes PostgreSQL service, role checks, restore rehearsal, Helm lint/render, Terraform provider validation, dependency and image scans. Validate on the actual runner; the source archive does not include a generated provider lockfile or hash-based Python lockfile. Review dependencies, pin action commit SHAs and base image digest, generate platform lockfiles, and commit after validation. Do not waive critical findings without formal exception.
- Decide supported EKS version, region, CIDRs (adjust network module if conflicts), retention, DB size, IAM access roles, OIDC provider and scopes, certificate issuing trust, ingress and monitoring components. The default VPC CIDR is 10.42.0.0/16; change before apply if overlapping. Only use private cluster/API with an approved management path. Ensure quotas and two AZs.

## 1. Bootstrap remote Terraform state

```bash
cd infra/terraform/state
terraform init
terraform validate
terraform plan -var='bucket_name=YOUR_GLOBALLY_UNIQUE_STATE_BUCKET' -out=state.tfplan
# Review plan and obtain authorization before:
terraform apply state.tfplan
```

Store bootstrap state securely (encrypted access-controlled backup); it initially uses local state. Protect state bucket IAM and restrict access to infrastructure operators. The AWS root uses S3 locking (`use_lockfile = true`), versioning, encryption, block-public-access and TLS-only policy. State may contain infrastructure metadata; never share it. No application DSN values are written by Terraform.

## 2. Plan and provision staging

```bash
cd ../aws
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
# Edit both with real values and approved cluster minor, admin role and recipient.
terraform init -backend-config=backend.hcl
terraform fmt -recursive
terraform validate
terraform plan -out=staging.tfplan
# Review IAM, network, costs, encryption, retention, deletion protection, and changes.
# Only after approval:
terraform apply staging.tfplan
terraform output
```

Generate/commit `.terraform.lock.hcl` after verifying provider checksums. State and plan files must stay private. Confirm SNS email subscription and test alarms. Check managed node groups and add-ons (including Pod Identity agent and VPC CNI network policy). Verify private endpoint reachability and RDS not publicly accessible. Scope egress, logging, VPC endpoints and node access to your organization. KMS defaults for RDS/ECR/SQS/S3 are service-managed encryption; customize for approved customer-managed key policies if required. SNS uses a customer-managed key. No auto-scaling controller or metrics-server is installed by Terraform.

## 3. Publish a scanned, signed image

Create or reuse the account GitHub OIDC provider `token.actions.githubusercontent.com` with audience `sts.amazonaws.com`. Set `github_oidc_provider_arn` and the **exact** approved `github_release_subject` in tfvars, then review and apply the IAM-only change. GitHub may use immutable owner/repository IDs in the `sub` claim; use your repository's actual subject, not a wildcard. Set repository/environment variables from Terraform outputs:

| Variable | Value |
|---|---|
| `AWS_RELEASE_ROLE_ARN` | `release_role_arn` |
| `AWS_REGION` | target region |
| `ECR_REPOSITORY` | `image_repository` |
| `SIGNATURE_REPOSITORY` | `signature_repository` |

Protect `main`, require CI and review, configure `release` environment approval and restrict it to `main`. Run **Signed image release** manually on `main`. It runs tests, scans the exact built image, creates CycloneDX SBOM, pushes SHA-tagged image, signs and verifies digest and SBOM attestation using scoped OIDC identity. Cosign v2 uses a separate signature repository (signature tags mutable; workload image tags immutable). Inspect and retain release artifacts; failure after push may leave an unsigned image, which must not be deployed. The workflow does not perform admission-time verification. Require an independent reviewer to verify signature and SBOM on the same digest before promotion, and add organization-approved admission policy before production. Never reuse mutable tags. Do not use public Sigstore transparency logs if organization policy forbids repository identity disclosure; use approved private signing infrastructure instead.

```bash
export COSIGN_REPOSITORY=YOUR_SIGNATURE_REPOSITORY
IMAGE='YOUR_ECR_REPOSITORY@sha256:VERIFIED_DIGEST'
IDENTITY='https://github.com/OWNER/REPO/.github/workflows/release.yaml@refs/heads/main'
cosign verify --certificate-identity "$IDENTITY" --certificate-oidc-issuer https://token.actions.githubusercontent.com "$IMAGE"
cosign verify-attestation --type cyclonedx --certificate-identity "$IDENTITY" --certificate-oidc-issuer https://token.actions.githubusercontent.com "$IMAGE"
```

Authenticate to ECR first using your read-only role. Consult release evidence and review vulnerability exceptions. Use patched tool versions and pin actions to reviewed commit SHAs before production.

## 4. Bootstrap database principals and trust

Use a short-lived, audited runner **inside the VPC** with approved access to the DB (RDS SG accepts the EKS cluster SG; arrange an approved runner or temporary narrowly scoped SG rule). It needs the RDS master secret read, read/put on runtime secrets, and no other database administration path. Obtain and validate the RDS CA bundle from the official AWS trust store (`https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem`); validate its trust chain and fingerprint against your organization's approved source. Do not disable TLS verification.

```bash
# from repo root, Terraform already initialized
terraform -chdir=infra/terraform/aws output -json database_secret_arns > /tmp/ledger-secret-arns.json
python scripts/bootstrap_database.py \
  --admin-secret-arn "$(terraform -chdir=infra/terraform/aws output -raw database_admin_secret_arn)" \
  --endpoint "$(terraform -chdir=infra/terraform/aws output -raw database_endpoint)" \
  --runtime-secret-arns-json /tmp/ledger-secret-arns.json \
  --ca-file /secure/path/global-bundle.pem
```

This creates five database roles and `ledger` schema owned by migrator. It generates random DSNs and writes directly to role-specific Secrets Manager containers; no values are printed or persisted locally. Secrets have `sslmode=verify-full&sslrootcert=/etc/rds-ca/global-bundle.pem`. The script refuses existing roles. If it fails after DB commit but before writing all secrets, stop; reconcile DB roles and Secrets Manager versions under admin change control, rotate missing or mismatched roles to new values and retry only the affected writes. Do not rerun blindly, expose the master secret, or delete data. Record completion in change ticket; remove temporary runner/SG access. Use separate credentials and controlled deployment restarts for rotation. Confirm actual privileges with integration tests; use migration owner only for jobs, not runtime.

## 5. Deploy cloud workloads

From approved management network and assumed admin role:

```bash
aws eks update-kubeconfig --region YOUR_REGION --name YOUR_CLUSTER
kubectl get nodes
kubectl create namespace ledger
kubectl label namespace ledger pod-security.kubernetes.io/enforce=restricted
kubectl -n ledger create configmap rds-ca --from-file=global-bundle.pem=/secure/path/global-bundle.pem
```

Configure an approved OIDC provider with audience for this API, RS256 access tokens, `scope` string including `ledger:write` or `ledger:operate`, `iss`, `aud`, `sub`, `iat`, `exp`. The chart does not provision an external provider. Configure short token lifetime, credential rotation and identity-to-role mapping. Use separate users/clients and controlled scopes. For external ingress use approved **private** ingress controller and DNS/TLS certificate with its namespace matching chart policy, and protect network paths. Ingress is disabled by default. The ingress TLS example assumes termination at controller; site-specific pod transport protection/mesh is a remaining review gate. `kubectl port-forward` may be used for approved synthetic internal testing, not a production access method.

Create `deploy/helm/ledger-cloud/values.staging.yaml` by copying `values.ci.yaml`, then replace all example values with actual Terraform outputs, image digest, OIDC values, and region. This file contains non-secret ARNs, URLs and image digest, not secret values. Verify namespace and service account names exactly `ledger`, `ledger-api`, `ledger-publisher`, `ledger-consumer`, `ledger-archive`, `ledger-migrator` (matching EKS Pod Identity). Mount CA config map. Optional HPA requires Metrics Server; ServiceMonitor requires Prometheus Operator. Restrict monitoring namespace access.

```bash
helm lint deploy/helm/ledger-cloud -f deploy/helm/ledger-cloud/values.staging.yaml
helm template ledger deploy/helm/ledger-cloud -n ledger -f deploy/helm/ledger-cloud/values.staging.yaml > /tmp/ledger-rendered.yaml
kubectl apply --dry-run=server -f /tmp/ledger-rendered.yaml -n ledger
```

**Preferred: Argo CD.** Install a supported Argo CD release via your platform team, configure trusted repository authentication and restrict RBAC. Copy and edit `deploy/gitops/project.yaml.example` and `application.yaml.example` (real repo URL). Review and apply to Argo namespace. Commit reviewed staging values/digest to main. Manually sync application after signature verification. Service accounts sync at wave -2, migration Job at -1, workloads at wave 0. Migration should succeed before new pods are scheduled. Verify Argo status and logs. A failed migration blocks promotion. Keep prior release digest and test schema compatibility before rollback; use expand/contract migrations for later changes.

**Helm-only evaluation:** use `helm template` for offline inspection. The Argo sync waves are the intended migration sequencing mechanism. Helm ignores Argo hook annotations; a Helm-only operator must independently sequence service accounts, migration Job and rollout, and manage resource ownership. Do not run a raw Helm install of the cloud chart expecting Argo ordering.

## 6. Observability and acceptance

Install a supported Prometheus Operator/Grafana stack and Alertmanager via approved platform tooling, enable ServiceMonitor with matching release selectors, apply `deploy/observability/prometheus-rules.yaml`, import Grafana JSON and select datasource. Optional OTLP collector config uses a private receiver and an authenticated HTTPS trace backend; inject backend auth through secret manager, never Git. Set app `observability.otlpEndpoint` only after collector configured. Verify EKS audit logs, application JSON logs, dashboard and alerts. Provision central log retention and alerts for Kubernetes failed Jobs. Test alert notification path. HPA needs Metrics Server and node autoscaling requires independently installed controller.

For a clean isolated staging environment, issue scoped test access tokens without pasting them into logs and run:

```bash
python scripts/cloud_smoke.py --base-url https://YOUR_PRIVATE_STAGING_HOST --confirm-synthetic-staging
python scripts/load_test.py --base-url https://YOUR_PRIVATE_STAGING_HOST --allow-nonlocal-synthetic --requests 200 --concurrency 8 --max-p95-ms 500
```

Inspect per-event database receipts, SQS visible/in-flight/DLQ metrics, archive Job and Object Lock retention with read-only roles. Validate pod restart, concurrent duplicate requests across replicas, poison-message redrive using dedicated disposable staging queue, loss of ACK, DB failover, RDS PITR and backup/restore. Use [operations runbook](operations-v2.md) and record evidence. Do not test fault injection in real business production.

## 7. Teardown and cost control

Quiesce clients, drain queue, complete audit archive and take approved snapshots before removal. Review Terraform destroy plan; RDS deletion protection must be deliberately changed and final snapshots retained. Object Lock COMPLIANCE versions cannot be removed until retention expiry, including during destroy. Maintain bucket and state until required retention ends. NAT/EKS/RDS costs continue until resources are removed. Use `terraform plan -destroy` as review, not automatic teardown. Never remove audit protections simply to clean up a demo.
