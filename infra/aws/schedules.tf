# The compose file's purge and refresh loops become EventBridge Scheduler runs of one-off tasks.

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    actions   = ["ecs:RunTask"]
    resources = [for k in ["purge", "refresh"] : "${aws_ecs_task_definition.job[k].arn_without_revision}:*"]
  }
  statement {
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.execution.arn, aws_iam_role.app.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "run-jobs"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

locals {
  schedules = {
    purge   = "cron(0 3 * * ? *)"   # daily: feedback older than feedback_retention_days
    refresh = "cron(0 4 ? * MON *)" # weekly: re-fetch downloadable sources; changed text goes back to review
  }
}

resource "aws_scheduler_schedule" "job" {
  for_each                     = local.schedules
  name                         = "${local.name}-${each.key}"
  schedule_expression          = each.value
  schedule_expression_timezone = "America/Los_Angeles"

  flexible_time_window { mode = "OFF" }

  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.scheduler.arn
    retry_policy { maximum_retry_attempts = 2 }

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.job[each.key].arn_without_revision
      launch_type         = "FARGATE"
      network_configuration {
        subnets          = [for s in aws_subnet.private : s.id]
        security_groups  = [aws_security_group.tasks.id]
        assign_public_ip = false
      }
    }
  }
}
