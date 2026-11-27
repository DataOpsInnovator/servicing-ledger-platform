# Secrets contain PostgreSQL DSNs; populate outside Terraform so values never enter state.
resource "aws_secretsmanager_secret" "database" {
  for_each                = local.roles
  name                    = "${var.name}/${each.key}/database-url"
  recovery_window_in_days = 30
}
resource "aws_iam_role" "workload" {
  for_each = local.roles
  name     = "${var.name}-${each.key}"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "pods.eks.amazonaws.com" }, Action = ["sts:AssumeRole", "sts:TagSession"] }] })
}
resource "aws_iam_role_policy" "workload" {
  for_each = local.roles
  role     = aws_iam_role.workload[each.key].id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat(
    [{ Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = aws_secretsmanager_secret.database[each.key].arn }],
    each.key == "publisher" ? [{ Effect = "Allow", Action = ["sqs:SendMessage"], Resource = aws_sqs_queue.events.arn }] : [],
    each.key == "consumer" ? [{ Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage"], Resource = aws_sqs_queue.events.arn }] : [],
    each.key == "archive" ? [{ Effect = "Allow", Action = ["s3:PutObject", "s3:GetObject"], Resource = "${aws_s3_bucket.audit.arn}/audit/v1/*" }] : []
  ) })
}
resource "aws_eks_pod_identity_association" "workload" {
  for_each        = local.roles
  cluster_name    = aws_eks_cluster.main.name
  namespace       = local.namespace
  service_account = "ledger-${each.key}"
  role_arn        = aws_iam_role.workload[each.key].arn
  depends_on      = [aws_eks_addon.core]
}
