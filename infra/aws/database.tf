# Postgres 16 with PostGIS and pgvector (both supported on RDS; migration 001 creates the extensions).
#
# The password is generated at apply time and sent only through write-only arguments, so it is never stored in
# Terraform state or plan files. It is written to Secrets Manager in the same apply and injected into the
# containers as PGPASSWORD, which libpq reads alongside DATABASE_URL.

ephemeral "random_password" "db" {
  length  = 40
  special = false
}

resource "aws_secretsmanager_secret" "db_password" {
  name                    = "${local.name}/db-password"
  description             = "Postgres password for the regengine user"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id                = aws_secretsmanager_secret.db_password.id
  secret_string_wo         = ephemeral.random_password.db.result
  secret_string_wo_version = var.db_password_version
}

resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = [for s in aws_subnet.private : s.id]
}

resource "aws_db_parameter_group" "main" {
  name   = "${local.name}-pg${var.db_engine_version}"
  family = "postgres${var.db_engine_version}"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
  # Statements are never written to the log, including on error: query parameters can hold addresses.
  parameter {
    name  = "log_min_error_statement"
    value = "panic"
  }
  parameter {
    name  = "log_statement"
    value = "none"
  }
  parameter {
    name  = "log_min_duration_statement"
    value = "-1"
  }
}

resource "aws_db_instance" "main" {
  identifier     = local.name
  engine         = "postgres"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  db_name                  = "regengine"
  username                 = "regengine"
  password_wo              = ephemeral.random_password.db.result
  password_wo_version      = var.db_password_version
  db_subnet_group_name     = aws_db_subnet_group.main.name
  vpc_security_group_ids   = [aws_security_group.db.id]
  parameter_group_name     = aws_db_parameter_group.main.name
  publicly_accessible      = false
  ca_cert_identifier       = "rds-ca-rsa2048-g1"
  delete_automated_backups = false

  storage_type          = "gp3"
  allocated_storage     = var.db_allocated_storage_gb
  max_allocated_storage = var.db_max_allocated_storage_gb
  storage_encrypted     = true

  multi_az                     = var.db_multi_az
  backup_retention_period      = var.db_backup_retention_days
  backup_window                = "09:00-10:00" # UTC, early morning in Los Angeles
  maintenance_window           = "sun:10:30-sun:11:30"
  copy_tags_to_snapshot        = true
  deletion_protection          = true
  skip_final_snapshot          = false
  final_snapshot_identifier    = "${local.name}-final"
  auto_minor_version_upgrade   = true
  apply_immediately            = false
  performance_insights_enabled = true # 7 days of history is free

  enabled_cloudwatch_logs_exports = ["postgresql"]
}

locals {
  # sslmode=require encrypts the connection; the password comes from PGPASSWORD (see above).
  database_url = "postgresql://regengine@${aws_db_instance.main.address}:5432/regengine?sslmode=require"
}
