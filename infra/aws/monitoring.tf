# Alarms go to one SNS topic. Metrics only: no request logs are kept anywhere, and the app logs carry status
# codes and opaque ids, never addresses or request bodies.

resource "aws_sns_topic" "alarms" {
  name = "${local.name}-alarms"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

data "aws_iam_policy_document" "alarms_topic" {
  statement {
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alarms.arn]
    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com", "events.amazonaws.com"]
    }
  }
}

resource "aws_sns_topic_policy" "alarms" {
  arn    = aws_sns_topic.alarms.arn
  policy = data.aws_iam_policy_document.alarms_topic.json
}

locals {
  alb_dims = { LoadBalancer = aws_lb.api.arn_suffix, TargetGroup = aws_lb_target_group.api.arn_suffix }
  ecs_dims = { ClusterName = aws_ecs_cluster.main.name, ServiceName = aws_ecs_service.api.name }
  db_dims  = { DBInstanceIdentifier = aws_db_instance.main.identifier }

  alarms = {
    api-5xx = {
      namespace = "AWS/ApplicationELB", metric = "HTTPCode_Target_5XX_Count", dims = local.alb_dims
      stat      = "Sum", threshold = 10, op = "GreaterThanThreshold", periods = 1
      text      = "More than 10 server errors from the API in 5 minutes"
    }
    api-latency-p95 = {
      namespace = "AWS/ApplicationELB", metric = "TargetResponseTime", dims = local.alb_dims
      stat      = "p95", threshold = 1.5, op = "GreaterThanThreshold", periods = 3
      text      = "API p95 response time over 1.5 s for 15 minutes"
    }
    api-no-healthy-tasks = {
      namespace = "AWS/ApplicationELB", metric = "HealthyHostCount", dims = local.alb_dims
      stat      = "Minimum", threshold = 1, op = "LessThanThreshold", periods = 1
      text      = "No healthy API task behind the load balancer"
    }
    api-memory = {
      namespace = "AWS/ECS", metric = "MemoryUtilization", dims = local.ecs_dims
      stat      = "Average", threshold = 85, op = "GreaterThanThreshold", periods = 3
      text      = "API memory above 85% for 15 minutes"
    }
    db-cpu = {
      namespace = "AWS/RDS", metric = "CPUUtilization", dims = local.db_dims
      stat      = "Average", threshold = 80, op = "GreaterThanThreshold", periods = 3
      text      = "Database CPU above 80% for 15 minutes"
    }
    db-storage = {
      namespace = "AWS/RDS", metric = "FreeStorageSpace", dims = local.db_dims
      stat      = "Minimum", threshold = 10 * 1024 * 1024 * 1024, op = "LessThanThreshold", periods = 1
      text      = "Database has under 10 GB free"
    }
    db-memory = {
      namespace = "AWS/RDS", metric = "FreeableMemory", dims = local.db_dims
      stat      = "Minimum", threshold = 256 * 1024 * 1024, op = "LessThanThreshold", periods = 3
      text      = "Database freeable memory under 256 MB"
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "main" {
  for_each            = local.alarms
  alarm_name          = "${local.name}-${each.key}"
  alarm_description   = each.value.text
  namespace           = each.value.namespace
  metric_name         = each.value.metric
  dimensions          = each.value.dims
  statistic           = contains(["Sum", "Average", "Minimum", "Maximum"], each.value.stat) ? each.value.stat : null
  extended_statistic  = contains(["Sum", "Average", "Minimum", "Maximum"], each.value.stat) ? null : each.value.stat
  period              = 300
  evaluation_periods  = each.value.periods
  threshold           = each.value.threshold
  comparison_operator = each.value.op
  treat_missing_data  = each.key == "api-no-healthy-tasks" ? "breaching" : "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
}

# A purge, refresh or migrate task that exits with an error.
resource "aws_cloudwatch_event_rule" "job_failed" {
  name = "${local.name}-job-failed"
  event_pattern = jsonencode({
    source      = ["aws.ecs"]
    detail-type = ["ECS Task State Change"]
    detail = {
      clusterArn = [aws_ecs_cluster.main.arn]
      lastStatus = ["STOPPED"]
      group      = [for k in keys(local.jobs) : "family:${local.name}-${k}"]
      containers = { exitCode = [{ "anything-but" = 0 }] }
    }
  })
}

resource "aws_cloudwatch_event_target" "job_failed" {
  rule = aws_cloudwatch_event_rule.job_failed.name
  arn  = aws_sns_topic.alarms.arn
  input_transformer {
    input_paths    = { group = "$.detail.group", reason = "$.detail.stoppedReason" }
    input_template = "\"${local.name}: job <group> failed (<reason>). See the /${local.name}/app log group.\""
  }
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = local.name
  dashboard_body = jsonencode({
    widgets = [
      for i, w in [
        { title = "Requests and server errors", metrics = [
          ["AWS/ApplicationELB", "RequestCountPerTarget", "TargetGroup", aws_lb_target_group.api.arn_suffix],
          ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", aws_lb.api.arn_suffix, "TargetGroup", aws_lb_target_group.api.arn_suffix],
        ], stat = "Sum" },
        { title = "API response time (p50, p95)", metrics = [
          ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", aws_lb.api.arn_suffix, "TargetGroup", aws_lb_target_group.api.arn_suffix, { stat = "p50" }],
          ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", aws_lb.api.arn_suffix, "TargetGroup", aws_lb_target_group.api.arn_suffix, { stat = "p95" }],
        ], stat = "p95" },
        { title = "API tasks: CPU and memory", metrics = [
          ["AWS/ECS", "CPUUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.api.name],
          ["AWS/ECS", "MemoryUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.api.name],
        ], stat = "Average" },
        { title = "Database: CPU and connections", metrics = [
          ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", aws_db_instance.main.identifier],
          ["AWS/RDS", "DatabaseConnections", "DBInstanceIdentifier", aws_db_instance.main.identifier],
        ], stat = "Average" },
        ] : {
        type   = "metric"
        x      = (i % 2) * 12
        y      = floor(i / 2) * 6
        width  = 12
        height = 6
        properties = {
          title   = w.title
          metrics = w.metrics
          stat    = w.stat
          period  = 300
          region  = var.region
        }
      }
    ]
  })
}
