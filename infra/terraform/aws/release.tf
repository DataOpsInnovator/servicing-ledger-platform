# Optional GitHub release identity. Supply the exact approved subject claim (including immutable
# owner/repo IDs where applicable) from GitHub's configured OIDC subject template.
variable "github_oidc_provider_arn" {
  type    = string
  default = ""
}
variable "github_release_subject" {
  type    = string
  default = ""
  validation {
    condition     = var.github_release_subject == "" || (startswith(var.github_release_subject, "repo:") && endswith(var.github_release_subject, ":environment:release") && !strcontains(var.github_release_subject, "*"))
    error_message = "Provide an exact repository release-environment subject; no wildcards."
  }
}
resource "aws_ecr_repository" "signatures" {
  name                 = "${var.name}-signatures"
  # Cosign v2 uses mutable attachment tags to append signatures/attestations.
  # Scope the exception to this dedicated repository, never workload images.
  #trivy:ignore:AWS-0031
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
}
resource "aws_iam_role" "release" {
  count = var.github_oidc_provider_arn != "" && var.github_release_subject != "" ? 1 : 0
  name  = "${var.name}-github-release"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Federated = var.github_oidc_provider_arn }, Action = "sts:AssumeRoleWithWebIdentity", Condition = { StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com", "token.actions.githubusercontent.com:sub" = var.github_release_subject } } }] })
}
resource "aws_iam_role_policy" "release" {
  count = length(aws_iam_role.release)
  role  = aws_iam_role.release[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "ecr:GetAuthorizationToken", Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:DescribeImages"], Resource = [aws_ecr_repository.main.arn, aws_ecr_repository.signatures.arn] }
  ] })
}
output "release_role_arn" { value = try(aws_iam_role.release[0].arn, null) }
output "signature_repository" { value = aws_ecr_repository.signatures.repository_url }
