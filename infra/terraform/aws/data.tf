resource "aws_security_group" "database" {
  name        = "${var.name}-database"
  description = "PostgreSQL only from EKS cluster security group"
  vpc_id      = aws_vpc.main.id
}
resource "aws_vpc_security_group_ingress_rule" "database" {
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = aws_eks_cluster.main.vpc_config[0].cluster_security_group_id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}
resource "aws_db_subnet_group" "main" {
  name       = var.name
  subnet_ids = aws_subnet.database[*].id
}
resource "aws_db_parameter_group" "main" {
  name   = "${var.name}-pg16"
  family = "postgres16"
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
}
resource "aws_db_instance" "main" {
  identifier                      = var.name
  engine                          = "postgres"
  engine_version                  = "16"
  instance_class                  = var.db_instance_class
  allocated_storage               = 30
  max_allocated_storage           = 100
  storage_type                    = "gp3"
  storage_encrypted               = true
  db_name                         = "ledger"
  username                        = "ledgeradmin"
  manage_master_user_password     = true
  multi_az                        = true
  publicly_accessible             = false
  db_subnet_group_name            = aws_db_subnet_group.main.name
  vpc_security_group_ids          = [aws_security_group.database.id]
  parameter_group_name            = aws_db_parameter_group.main.name
  backup_retention_period         = 14
  copy_tags_to_snapshot           = true
  deletion_protection             = true
  skip_final_snapshot             = false
  final_snapshot_identifier       = "${var.name}-final"
  auto_minor_version_upgrade      = true
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  apply_immediately               = false
}
resource "aws_sqs_queue" "dead" {
  name                      = "${var.name}-dlq"
  sqs_managed_sse_enabled   = true
  message_retention_seconds = 1209600
}
resource "aws_sqs_queue" "events" {
  name                       = "${var.name}-events"
  sqs_managed_sse_enabled    = true
  visibility_timeout_seconds = 120
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 10
  redrive_policy = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dead.arn, maxReceiveCount = 5 })
}
resource "aws_sqs_queue_redrive_allow_policy" "dead" {
  queue_url = aws_sqs_queue.dead.id
  redrive_allow_policy = jsonencode({ redrivePermission = "byQueue", sourceQueueArns = [aws_sqs_queue.events.arn] })
}
resource "aws_sqs_queue_policy" "tls" {
  for_each  = { events = aws_sqs_queue.events, dead = aws_sqs_queue.dead }
  queue_url = each.value.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Sid = "DenyInsecureTransport", Effect = "Deny", Principal = "*", Action = "sqs:*", Resource = each.value.arn, Condition = { Bool = { "aws:SecureTransport" = "false" } } }] })
}
resource "aws_ecr_repository" "main" {
  name                 = var.name
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
}
resource "aws_s3_bucket" "audit" {
  bucket              = "${var.name}-${data.aws_caller_identity.current.account_id}-${var.region}-audit"
  object_lock_enabled = true
  force_destroy       = false
}
resource "aws_s3_bucket_versioning" "audit" {
  bucket = aws_s3_bucket.audit.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_object_lock_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    default_retention {
      mode = "COMPLIANCE"
      days = var.audit_retention_days
    }
  }
  depends_on = [aws_s3_bucket_versioning.audit]
}
resource "aws_s3_bucket_public_access_block" "audit" {
  bucket                  = aws_s3_bucket.audit.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.audit.arn
    }
    bucket_key_enabled = true
  }
}
resource "aws_s3_bucket_policy" "audit" {
  bucket = aws_s3_bucket.audit.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Sid = "DenyInsecureTransport", Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.audit.arn, "${aws_s3_bucket.audit.arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } }] })
}

resource "aws_kms_key" "audit" {
  description             = "Servicing ledger audit archive"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  lifecycle { prevent_destroy = true }
}
