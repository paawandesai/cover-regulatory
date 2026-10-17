# Applies the whole stack to mocked providers: no AWS account or credentials are used, and nothing is created.
# Run with: terraform init -backend=false && terraform test

mock_provider "aws" {
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/mock" }
  }
  mock_resource "aws_sns_topic" {
    defaults = { arn = "arn:aws:sns:us-west-2:123456789012:mock" }
  }
  mock_resource "aws_ecs_cluster" {
    defaults = { arn = "arn:aws:ecs:us-west-2:123456789012:cluster/mock" }
  }
  mock_resource "aws_lb" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-west-2:123456789012:loadbalancer/app/mock/0123456789abcdef" }
  }
  mock_resource "aws_lb_target_group" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-west-2:123456789012:targetgroup/mock/0123456789abcdef" }
  }
  mock_resource "aws_lb_listener" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-west-2:123456789012:listener/app/mock/0123456789abcdef/0123456789abcdef" }
  }
  mock_resource "aws_secretsmanager_secret" {
    defaults = { arn = "arn:aws:secretsmanager:us-west-2:123456789012:secret:mock" }
  }
  mock_resource "aws_s3_bucket" {
    defaults = { arn = "arn:aws:s3:::mock" }
  }
  mock_resource "aws_db_instance" {
    defaults = { arn = "arn:aws:rds:us-west-2:123456789012:db:mock" }
  }
  mock_resource "aws_backup_plan" {
    defaults = { arn = "arn:aws:backup:us-west-2:123456789012:backup-plan:mock" }
  }
  mock_resource "aws_cloudfront_function" {
    defaults = { arn = "arn:aws:cloudfront::123456789012:function/mock" }
  }
  mock_resource "aws_ecs_task_definition" {
    defaults = {
      arn                  = "arn:aws:ecs:us-west-2:123456789012:task-definition/mock:1"
      arn_without_revision = "arn:aws:ecs:us-west-2:123456789012:task-definition/mock"
    }
  }
  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-west-2:123456789012:certificate/mock"
      domain_validation_options = [{
        domain_name           = "regengine.example.com"
        resource_record_name  = "_x.regengine.example.com."
        resource_record_type  = "CNAME"
        resource_record_value = "_y.acm-validations.aws."
      }]
    }
  }
  override_data {
    target = data.aws_availability_zones.available
    values = { names = ["us-west-2a", "us-west-2b", "us-west-2c"] }
  }
  override_data {
    target = data.aws_ec2_managed_prefix_list.cloudfront
    values = { id = "pl-82a045eb" }
  }
  override_data {
    target = data.aws_iam_policy_document.ecs_tasks_assume
    values = { json = "{}" }
  }
  override_data {
    target = data.aws_iam_policy_document.read_secrets
    values = { json = "{}" }
  }
  override_data {
    target = data.aws_iam_policy_document.read_dumps
    values = { json = "{}" }
  }
  override_data {
    target = data.aws_iam_policy_document.web_bucket
    values = { json = "{}" }
  }
  override_data {
    target = data.aws_iam_policy_document.scheduler_assume
    values = { json = "{}" }
  }
  override_data {
    target = data.aws_iam_policy_document.scheduler
    values = { json = "{}" }
  }
  override_data {
    target = data.aws_iam_policy_document.alarms_topic
    values = { json = "{}" }
  }
  override_data {
    target = data.aws_iam_policy_document.backup_assume
    values = { json = "{}" }
  }
}

mock_provider "aws" {
  alias = "us_east_1"
  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-1:123456789012:certificate/mock"
      domain_validation_options = [{
        domain_name           = "regengine.example.com"
        resource_record_name  = "_x.regengine.example.com."
        resource_record_type  = "CNAME"
        resource_record_value = "_y.acm-validations.aws."
      }]
    }
  }
  mock_resource "aws_acm_certificate_validation" {
    defaults = { certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/mock" }
  }
  mock_resource "aws_wafv2_web_acl" {
    defaults = { arn = "arn:aws:wafv2:us-east-1:123456789012:global/webacl/mock/0123" }
  }
}

# The random provider is real: it runs locally, and mocks do not support its ephemeral password.

variables {
  domain_name    = "regengine.example.com"
  hosted_zone_id = "Z0000000000000000000"
  api_image_tag  = "test"
}

run "production_defaults" {
  command = apply # against the mocks: nothing is created

  assert {
    condition     = length(aws_subnet.private) == 2 && length(aws_nat_gateway.main) == 2
    error_message = "Two zones, each with its own NAT gateway."
  }
  assert {
    condition = (aws_db_instance.main.multi_az && aws_db_instance.main.deletion_protection
    && aws_db_instance.main.storage_encrypted && !aws_db_instance.main.publicly_accessible)
    error_message = "The database is Multi-AZ, encrypted, private and protected from deletion."
  }
  assert {
    condition     = aws_db_instance.main.backup_retention_period == 14
    error_message = "Point-in-time recovery covers 14 days."
  }
  assert {
    condition     = length(aws_backup_plan.db.rule) == 2
    error_message = "Daily and monthly AWS Backup rules."
  }
  assert {
    condition     = aws_appautoscaling_target.api.min_capacity == 2 && aws_appautoscaling_target.api.max_capacity == 10
    error_message = "The API scales between 2 and 10 tasks."
  }
  assert {
    condition = alltrue([for c in jsondecode(aws_ecs_task_definition.api.container_definitions) :
    contains([for e in c.environment : "${e.name}=${e.value}"], "TRUSTED_PROXY_HOPS=2")])
    error_message = "The API counts CloudFront and the ALB as proxies."
  }
  assert {
    condition = !contains(flatten([for c in jsondecode(aws_ecs_task_definition.api.container_definitions) :
    [for s in c.secrets : s.name]]), "ANTHROPIC_COVER_API_KEY")
    error_message = "The chat key is not passed unless enable_chat is set."
  }
  assert {
    condition = alltrue([for r in aws_wafv2_web_acl.main.rule :
    !r.visibility_config[0].sampled_requests_enabled])
    error_message = "WAF request sampling stays off (it records query strings, which hold addresses)."
  }
  assert {
    condition     = length(aws_cloudfront_distribution.main.logging_config) == 0
    error_message = "CloudFront access logs stay off."
  }
  assert {
    condition     = length(aws_lb.api.access_logs) == 0 || !aws_lb.api.access_logs[0].enabled
    error_message = "ALB access logs stay off."
  }
  assert {
    condition     = length(aws_sns_topic_subscription.email) == 0
    error_message = "No email subscription without alarm_email."
  }
}

run "small_staging" {
  command = apply # against the mocks: nothing is created
  variables {
    environment        = "staging"
    single_nat_gateway = true
    db_multi_az        = false
    enable_chat        = true
    enable_invite_gate = false
    alarm_email        = "ops@example.com"
  }

  assert {
    condition     = length(aws_nat_gateway.main) == 1 && length(aws_route_table.private) == 2
    error_message = "One NAT gateway shared by both private subnets."
  }
  assert {
    condition = contains(flatten([for c in jsondecode(aws_ecs_task_definition.api.container_definitions) :
    [for s in c.secrets : s.name]]), "ANTHROPIC_COVER_API_KEY")
    error_message = "enable_chat passes the key secret."
  }
  assert {
    condition     = length(aws_secretsmanager_secret.invite_code) == 0
    error_message = "No invite secret without the gate."
  }
}
