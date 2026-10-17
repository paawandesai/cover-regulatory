resource "aws_ecs_cluster" "main" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = var.container_insights ? "enabled" : "disabled"
  }
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/${local.name}/app"
  retention_in_days = 30
}

# --- roles --------------------------------------------------------------------------------------------------

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Used by ECS to pull images, write logs and read the secrets it injects.
resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "read_secrets" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = distinct([for s in local.app_secrets : s.valueFrom])
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "read-app-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.read_secrets.json
}

# The API and its jobs call no AWS APIs, so their task role has no permissions.
resource "aws_iam_role" "app" {
  name               = "${local.name}-app"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

# The restore task reads dumps from the data bucket.
resource "aws_iam_role" "dbtool" {
  name               = "${local.name}-dbtool"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "read_dumps" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data.arn}/dumps/*"]
  }
}

resource "aws_iam_role_policy" "dbtool" {
  name   = "read-dumps"
  role   = aws_iam_role.dbtool.id
  policy = data.aws_iam_policy_document.read_dumps.json
}

# --- task definitions ---------------------------------------------------------------------------------------

locals {
  api_image = "${aws_ecr_repository.api.repository_url}:${var.api_image_tag}"
  log_config = {
    logDriver = "awslogs"
    options = {
      awslogs-group         = aws_cloudwatch_log_group.app.name
      awslogs-region        = var.region
      awslogs-stream-prefix = "app"
    }
  }
  base_env = [
    { name = "DATABASE_URL", value = local.database_url },
    { name = "LLM_MODEL_ID", value = var.llm_model_id },
  ]
  # Commands for the scheduled and one-off jobs; each runs the API image.
  jobs = {
    migrate = { command = ["python", "-m", "app.db.migrate"], env = [] }
    purge = {
      command = ["python", "-m", "app.api.purge"]
      env     = [{ name = "FEEDBACK_RETENTION_DAYS", value = tostring(var.feedback_retention_days) }]
    }
    refresh = {
      command = ["python", "-m", "app.ingest.regtext.refresh"]
      env     = [{ name = "REGTEXT_RAW_DIR", value = "/tmp/regtext" }]
    }
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.app.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name         = "api"
    image        = local.api_image
    essential    = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment = concat(local.base_env, [
      { name = "ADMIN_USERNAME", value = var.admin_username },
      { name = "TRUST_PROXY_HEADERS", value = "true" },
      { name = "TRUSTED_PROXY_HOPS", value = "2" }, # CloudFront, then the ALB
    ])
    secrets          = local.app_secrets
    logConfiguration = local.log_config
    stopTimeout      = 30
  }])
}

resource "aws_ecs_task_definition" "job" {
  for_each                 = local.jobs
  family                   = "${local.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 4096
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.app.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name             = each.key
    image            = local.api_image
    essential        = true
    command          = each.value.command
    environment      = concat(local.base_env, each.value.env)
    secrets          = local.job_secrets
    logConfiguration = local.log_config
  }])
}

resource "aws_ecs_task_definition" "restore" {
  family                   = "${local.name}-restore"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.dbtool.arn
  ephemeral_storage { size_in_gib = 30 }
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "restore"
    image     = "${aws_ecr_repository.dbtool.repository_url}:${var.dbtool_image_tag}"
    essential = true
    environment = [
      { name = "DATABASE_URL", value = local.database_url },
      { name = "DATA_BUCKET", value = aws_s3_bucket.data.bucket },
      { name = "DUMP_KEY", value = "" }, # set per run: infra/aws/restore.sh
    ]
    secrets          = local.job_secrets
    logConfiguration = local.log_config
  }])
}

# --- API service --------------------------------------------------------------------------------------------

resource "aws_ecs_service" "api" {
  name                              = "api"
  cluster                           = aws_ecs_cluster.main.id
  task_definition                   = aws_ecs_task_definition.api.arn
  desired_count                     = var.api_min_tasks
  launch_type                       = "FARGATE"
  health_check_grace_period_seconds = 90 # the embedding model loads at start-up
  propagate_tags                    = "SERVICE"

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = [for s in aws_subnet.private : s.id]
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  lifecycle {
    ignore_changes = [desired_count] # owned by autoscaling
  }
  depends_on = [aws_lb_listener_rule.from_cloudfront]
}

resource "aws_appautoscaling_target" "api" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = var.api_min_tasks
  max_capacity       = var.api_max_tasks
}

resource "aws_appautoscaling_policy" "api_cpu" {
  name               = "cpu"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.api.service_namespace
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  target_tracking_scaling_policy_configuration {
    target_value       = 60
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}

# Assessments are CPU-bound (about 260 ms each at p50), so requests per task is the earlier signal.
resource "aws_appautoscaling_policy" "api_requests" {
  name               = "requests"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.api.service_namespace
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  target_tracking_scaling_policy_configuration {
    target_value       = 120 # per task per minute
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      resource_label         = "${aws_lb.api.arn_suffix}/${aws_lb_target_group.api.arn_suffix}"
    }
  }
}
