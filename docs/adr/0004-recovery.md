# ADR-0004: Backup-and-restore regional recovery

- **Status:** Accepted for portfolio; warm standby is an enterprise option.
- **Context:** Regional redundancy adds continuous cost and operational complexity; the personal portfolio should prove restore and reconciliation first.
- **Decision:** Use multi-AZ service resilience within the primary region and backup-and-restore for region loss. Proposed region-loss target is 8h RTO / 24h RPO, not validated.
- **Alternatives:** Pilot light; warm standby; active/passive; active/active.
- **Rationale:** Restore-based recovery is affordable and forces explicit recovery-point and transaction-reconciliation work.
- **Consequences:** Longer recovery and nonzero data loss window; backup copies and restore procedures must be independently protected and measured.
- **Security / operations:** Separate backup permissions, encryption, restore destination isolation, approval gates, and evidence preservation.
- **Cost:** Periodic backup-copy and storage charges remain; warm standby would add continuous compute/database/network cost.
- **Revisit when:** Business-approved objectives require faster recovery or less data loss and measured restore cannot meet them.

