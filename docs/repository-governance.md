# Repository governance and release checklist

This policy documents intended controls. Repository settings must be enforced independently by the GitHub owner; a committed document does not configure them.

## Change control

- Protect main against direct pushes, force pushes and deletion; require pull requests, conversation resolution, and up-to-date branches.
- Require successful checks: application (3.12), application (3.13), postgres, security, deployment. Select the actual GitHub Actions check contexts when configuring protection.
- For a solo-maintained portfolio, independent review may not be available; for a team, require an independent reviewer. Do not bypass a failing check.
- Keep synthetic fixtures only. Enable dependency graph, Dependabot alerts/security updates, secret scanning and push protection wherever available. Enable private vulnerability reporting before directing reporters to it.
- Keep AWS deployment and release credentials separate; use the protected release environment with approved OIDC identity. Do not provision cloud resources without budget and explicit authorization.

## Release procedure

1. Verify all five CI jobs on the exact candidate commit and check that main is current.
2. Review license, changes, release notes and any security exceptions (including the narrowly scoped Cosign attachment-tag exception).
3. Verify post-merge main CI. Record the full commit SHA and workflow run URL.
4. Create an annotated v2.0.0 tag and publish the GitHub release against that validated commit. Do not claim a release exists before publication.
5. Treat cloud image signing and deployment as separate, explicitly approved operations.

## Evidence and settings

- [CI workflow](../.github/workflows/ci.yaml)
- [Evidence register](evidence/README.md)
- [Branch settings](https://github.com/DataOpsInnovator/servicing-ledger-platform/settings/branches)
- [Security settings](https://github.com/DataOpsInnovator/servicing-ledger-platform/settings/security_analysis)
- [Release page](https://github.com/DataOpsInnovator/servicing-ledger-platform/releases)
- [Security policy](../SECURITY.md)
- [License](../LICENSE)

Administrative settings, release creation, and profile pinning must be verified in GitHub; this document is not evidence of their activation.
