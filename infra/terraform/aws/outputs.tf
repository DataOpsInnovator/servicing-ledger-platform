output "cluster_name" { value = aws_eks_cluster.main.name }
output "database_endpoint" { value = aws_db_instance.main.address }
output "database_admin_secret_arn" { value = aws_db_instance.main.master_user_secret[0].secret_arn }
output "database_secret_arns" { value = { for k, v in aws_secretsmanager_secret.database : k => v.arn } }
output "queue_url" { value = aws_sqs_queue.events.id }
output "dlq_url" { value = aws_sqs_queue.dead.id }
output "audit_bucket" { value = aws_s3_bucket.audit.bucket }
output "image_repository" { value = aws_ecr_repository.main.repository_url }
