variable "region" {
  description = "Region for the VPC, database and containers."
  type        = string
  default     = "us-west-2"
}

variable "environment" {
  description = "Short environment name used in resource names, such as prod or staging."
  type        = string
  default     = "prod"
}

variable "domain_name" {
  description = "Public hostname of the app, such as regengine.example.com. The ALB is reached at origin.<domain_name>."
  type        = string
}

variable "hosted_zone_id" {
  description = "Route 53 hosted zone that holds domain_name."
  type        = string
}

variable "alarm_email" {
  description = "Address that receives alarm emails (confirm the subscription once). Empty means no email."
  type        = string
  default     = ""
}

variable "api_image_tag" {
  description = "Tag of the API image in ECR to run, normally the git commit."
  type        = string
}

variable "dbtool_image_tag" {
  description = "Tag of the restore tool image in ECR (deploy/dbtool.Dockerfile)."
  type        = string
  default     = "latest-build"
}

variable "az_count" {
  description = "Availability zones to spread subnets across."
  type        = number
  default     = 2
}

variable "single_nat_gateway" {
  description = "One NAT gateway instead of one per zone. Cheaper, but outbound access stops if that zone fails."
  type        = bool
  default     = false
}

variable "db_instance_class" {
  type    = string
  default = "db.m7g.large"
}

variable "db_engine_version" {
  description = "Postgres major version; the dumps and CI use 16."
  type        = string
  default     = "16"
}

variable "db_allocated_storage_gb" {
  type    = number
  default = 50
}

variable "db_max_allocated_storage_gb" {
  description = "Storage autoscaling ceiling."
  type        = number
  default     = 200
}

variable "db_multi_az" {
  type    = bool
  default = true
}

variable "db_backup_retention_days" {
  description = "Point-in-time recovery window for RDS automated backups (AWS Backup keeps longer copies)."
  type        = number
  default     = 14
}

variable "db_password_version" {
  description = "Increase by one to set a new database password on the next apply (see README, Rotating secrets)."
  type        = number
  default     = 1
}

variable "api_cpu" {
  type    = number
  default = 1024
}

variable "api_memory" {
  description = "MiB. The embedding model is loaded in each API process."
  type        = number
  default     = 4096
}

variable "api_min_tasks" {
  type    = number
  default = 2
}

variable "api_max_tasks" {
  type    = number
  default = 10
}

variable "admin_username" {
  description = "Shared admin account for Rule review; named reviewers are added with python -m app.api.reviewers."
  type        = string
  default     = "reviewer"
}

variable "enable_invite_gate" {
  description = "Require the invite code on every API route except health (the hosted demo's behaviour)."
  type        = bool
  default     = true
}

variable "enable_chat" {
  description = "Pass ANTHROPIC_COVER_API_KEY to the API so the follow-up chat works. Needs the secret to hold a key."
  type        = bool
  default     = false
}

variable "llm_model_id" {
  type    = string
  default = "claude-opus-5-5"
}

variable "feedback_retention_days" {
  type    = number
  default = 14
}

variable "waf_rate_limit" {
  description = "Requests per viewer IP in any 5 minutes before the WAF blocks it."
  type        = number
  default     = 2000
}

variable "waf_auth_rate_limit" {
  description = "Requests per viewer IP in any 5 minutes to /api/invite and /api/admin. Shared across API tasks."
  type        = number
  default     = 100
}

variable "noindex" {
  description = "Send X-Robots-Tag: noindex, as the demo does."
  type        = bool
  default     = true
}

variable "container_insights" {
  description = "ECS Container Insights (billed per metric)."
  type        = bool
  default     = true
}
