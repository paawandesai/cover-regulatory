# Secrets whose values are set by an operator, never by Terraform, so no value ever reaches state or git:
#   aws secretsmanager put-secret-value --secret-id <name> --secret-string file://value.txt
# Each one must hold a value before the API service first starts (README.md, First deploy).

resource "aws_secretsmanager_secret" "admin_password_scrypt" {
  name                    = "${local.name}/admin-password-scrypt"
  description             = "scrypt hash of the shared admin password (python -m app.api.auth)"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret" "invite_code" {
  count                   = var.enable_invite_gate ? 1 : 0
  name                    = "${local.name}/demo-invite-code"
  description             = "Invite code that gates the API"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret" "anthropic_key" {
  count                   = var.enable_chat ? 1 : 0
  name                    = "${local.name}/anthropic-api-key"
  description             = "Anthropic API key for the follow-up chat"
  recovery_window_in_days = 7
}

# A random value CloudFront sends to the ALB, so the ALB answers only requests that came through CloudFront
# (and its WAF). It is not a user credential; it lives in state, which is encrypted in the state bucket.
resource "random_password" "origin_verify" {
  length  = 48
  special = false
}

locals {
  app_secrets = concat(
    [
      { name = "PGPASSWORD", valueFrom = aws_secretsmanager_secret.db_password.arn },
      { name = "ADMIN_PASSWORD_SCRYPT", valueFrom = aws_secretsmanager_secret.admin_password_scrypt.arn },
    ],
    [for s in aws_secretsmanager_secret.invite_code : { name = "DEMO_INVITE_CODE", valueFrom = s.arn }],
    [for s in aws_secretsmanager_secret.anthropic_key : { name = "ANTHROPIC_COVER_API_KEY", valueFrom = s.arn }],
  )
  # Jobs need only the database.
  job_secrets = [{ name = "PGPASSWORD", valueFrom = aws_secretsmanager_secret.db_password.arn }]
}
