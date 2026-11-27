variable "region" {
  type    = string
  default = "us-east-1"
}
variable "name" {
  type    = string
  default = "servicing-ledger"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,25}$", var.name))
    error_message = "Use a short lowercase name."
  }
}
variable "environment" {
  type    = string
  default = "staging"
}
variable "cluster_version" {
  type        = string
  description = "Select a currently supported EKS minor version in your region."
}
variable "admin_role_arn" {
  type        = string
  description = "Existing trusted IAM role for cluster administration."
}
variable "public_api_cidrs" {
  type        = list(string)
  default     = []
  description = "Empty keeps Kubernetes API private. If necessary, supply approved narrow IPv4 CIDRs."
  validation {
    condition     = alltrue([for cidr in var.public_api_cidrs : can(cidrnetmask(cidr)) && !contains(["0.0.0.0/0"], cidr) && try(tonumber(split("/", cidr)[1]) >= 24, false)])
    error_message = "Public access must use approved narrow IPv4 CIDRs (/24 or narrower)."
  }
}
variable "audit_retention_days" {
  type    = number
  default = 365
  validation {
    condition     = var.audit_retention_days >= 1 && var.audit_retention_days <= 3650
    error_message = "Retention must be 1–3650 days; validate legal policy independently."
  }
}
variable "alert_email" {
  type        = string
  description = "Operations SNS subscription; recipient must confirm."
}
variable "node_instance_type" {
  type    = string
  default = "m6i.large"
}
variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}
