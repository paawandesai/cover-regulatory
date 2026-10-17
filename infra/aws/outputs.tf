# Read by deploy.sh and restore.sh.

output "url" {
  value = "https://${var.domain_name}"
}

output "region" {
  value = var.region
}

output "cluster" {
  value = aws_ecs_cluster.main.name
}

output "api_service" {
  value = aws_ecs_service.api.name
}

output "api_repository" {
  value = aws_ecr_repository.api.repository_url
}

output "dbtool_repository" {
  value = aws_ecr_repository.dbtool.repository_url
}

output "job_families" {
  value = merge(
    { for k, td in aws_ecs_task_definition.job : k => td.family },
    { restore = aws_ecs_task_definition.restore.family },
  )
}

output "private_subnets" {
  value = [for s in aws_subnet.private : s.id]
}

output "tasks_security_group" {
  value = aws_security_group.tasks.id
}

output "web_bucket" {
  value = aws_s3_bucket.web.bucket
}

output "data_bucket" {
  value = aws_s3_bucket.data.bucket
}

output "distribution_id" {
  value = aws_cloudfront_distribution.main.id
}

output "secrets_to_fill" {
  description = "Secrets an operator must put a value in before the first deploy."
  value = concat(
    [aws_secretsmanager_secret.admin_password_scrypt.name],
    [for s in aws_secretsmanager_secret.invite_code : s.name],
    [for s in aws_secretsmanager_secret.anthropic_key : s.name],
  )
}

output "db_endpoint" {
  value = aws_db_instance.main.address
}
