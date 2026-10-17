# Production setup on AWS

This is Terraform for running the engine on AWS. It has **not been applied**. It is checked in CI with `terraform validate` and with a test that applies the whole stack to mocked providers, which proves the configuration hangs together but not that AWS accepts every value. A first apply in a sandbox account will turn up the rest.

```
Users ─► CloudFront + WAF ─┬─► S3 (built web app, private, read through origin access control)
                           └─► /api/* ─► ALB (CloudFront ranges + origin header only)
                                          └─► API on ECS Fargate (2 to 10 tasks, private subnets)
                                                 └─► RDS Postgres 16 + PostGIS + pgvector (Multi-AZ, private)
EventBridge Scheduler ─► purge (daily) and refresh (weekly) tasks, same image
CloudWatch alarms and job failures ─► SNS ─► email        AWS Backup ─► daily and monthly snapshots
```

| File | What it creates |
|---|---|
| `network.tf` | VPC across 2 zones, public subnets for the ALB and NAT, private subnets for tasks and the database, an S3 gateway endpoint, security groups |
| `database.tf` | RDS Postgres 16: Multi-AZ, encrypted, TLS required, deletion protection, 14-day point-in-time recovery, storage autoscaling, no statement logging |
| `secrets.tf` | Secrets Manager entries for the admin password hash, the invite code and (if `enable_chat`) the Anthropic key; values are put in by hand |
| `ecr.tf` | Image repositories and the private data bucket for dumps |
| `ecs.tf` | Cluster, the API service with rolling deploys and automatic rollback, CPU and request-count autoscaling, and job task definitions (migrate, purge, refresh, restore) |
| `alb.tf` | The ALB on `origin.<domain>`, which forwards only requests carrying CloudFront's origin-verify header |
| `cdn.tf` | CloudFront, the web bucket, the single-page-app rewrite, security headers, DNS and certificates |
| `waf.tf` | WAF: per-IP rate limits (overall, and stricter on `/api/invite` and `/api/admin`), AWS IP reputation, common and known-bad-input rules |
| `schedules.tf` | Daily purge and weekly source check |
| `monitoring.tf` | Alarms (server errors, p95 latency, no healthy task, API memory, database CPU, storage and memory), job-failure events, a dashboard |
| `backup.tf` | AWS Backup: daily snapshots kept 35 days, monthly kept a year |

## Rules carried over from the demo
- **No request logs anywhere.** Query strings and bodies hold addresses, so CloudFront, ALB and WAF request logs and WAF request sampling are off, and Postgres never logs statements. Only metrics are kept. The app's own logs (CloudWatch, 30 days) carry status codes and opaque ids, as on the demo.
- **No secret in git or in Terraform state.** The database password is generated at apply time and passed only through write-only arguments. The admin hash, invite code and Anthropic key are put into Secrets Manager by an operator. The only generated value in state is the CloudFront-to-ALB origin header, and state sits in an encrypted bucket.
- **Dumps stay private.** They hold hand-saved regulation text, so they go only to the private data bucket.
- **The chat stays off** unless `enable_chat = true` and the key secret has a value.
- **The admin screens keep their real sign-in**, and the WAF adds a shared rate limit on top.

## Cost
Estimated from on-demand list prices in us-west-2 at low traffic, before tax and data transfer. Check the AWS Pricing Calculator before applying.

| Part | About per month |
|---|---|
| RDS db.m7g.large Multi-AZ, 50 GB gp3 | $260 |
| Fargate, 2 API tasks (1 vCPU, 4 GB) running all the time | $85 |
| NAT gateways (2) | $70 |
| ALB | $25 |
| WAF (web ACL, 5 rules, requests) | $12 |
| CloudFront, Secrets Manager, CloudWatch, Backup storage, Container Insights | $20 to $40 |
| **Total** | **about $470** |

A smaller staging setup (`db_multi_az = false`, `db_instance_class = "db.t4g.medium"`, `single_nat_gateway = true`, `api_min_tasks = 1`) comes to about $170.

## First deploy
Prerequisites: an AWS account, a Route 53 hosted zone for the domain, the AWS CLI signed in, Docker, Node 22, Terraform 1.11 or later, and `jq`.

1. Create a versioned, encrypted S3 bucket for Terraform state. Copy `backend.hcl.example` to `backend.hcl` and `terraform.tfvars.example` to `terraform.tfvars`, then fill both in. Neither is committed.
2. `terraform init -backend-config=backend.hcl`
3. `terraform apply -var api_image_tag=bootstrap -target=aws_ecr_repository.api -target=aws_ecr_repository.dbtool -target=aws_secretsmanager_secret.admin_password_scrypt -target=aws_secretsmanager_secret.invite_code` creates the image repositories and the empty secrets.
4. Fill the secrets that `terraform output secrets_to_fill` lists. Create the admin hash with `cd backend && uv run python -m app.api.auth`. Then put each value in with `aws secretsmanager put-secret-value --secret-id <name> --secret-string file://value.txt`, and delete the file afterwards.
5. `./deploy.sh` builds and pushes the images, creates everything else, runs the migrations, starts the API and publishes the web app.
6. `./restore.sh /path/to/regengine.dump` loads the regulation data (`scripts/db-dump.sh` makes the dump). After that, `/api/health` shows the rule and chunk counts.
7. Confirm the alarm email subscription.

## Routine work
- **Deploy a commit:** `./deploy.sh`. Migrations run first with the new image. The API then rolls over one task at a time and rolls back on its own if new tasks fail the health check.
- **Load a new dump:** `./restore.sh <file>`.
- **Run a job now:** `./run-task.sh refresh`, `./run-task.sh purge` or `./run-task.sh migrate`.
- **Add a named reviewer:** run `python -m app.api.reviewers add` as a one-off task with ECS Exec, or from a machine that can reach the database.

## Restoring the database
- **To a point in time within 14 days:** use `aws rds restore-db-instance-to-point-in-time` into a new instance. Then either swap names, or point `DATABASE_URL` at the new instance by importing it into state.
- **From a daily or monthly snapshot:** restore it in AWS Backup (vault `regengine-<environment>`) into a new instance, the same way.
- **To rebuild from scratch:** create a new instance, then run `./restore.sh` with the latest dump. The regulation data comes from that dump. Feedback, reports, reviewers and the audit log come only from backups.

## Rotating secrets
- **Database password:** raise `db_password_version` by one and run `terraform apply`. Then run `aws ecs update-service --force-new-deployment` so running tasks pick it up. Tasks still using the old password fail until they are replaced.
- **Admin hash, invite code or Anthropic key:** put a new value in the secret, then force a new deployment.
- **Origin header:** `terraform apply -replace=random_password.origin_verify`. CloudFront and the ALB update in the same apply, and a few requests may get a 403 while CloudFront propagates.

## Not included
- **SSO for reviewers:** this needs Cover's identity provider. The ALB can authenticate with OIDC in front of `/api/admin` once one is chosen.
- **A shared assessment cache (ElastiCache):** the API has no cache layer yet. An assessment takes about 260 ms (p50) and scales with tasks.
- **Queue-based ingestion and model extraction in AWS:** extraction still runs from a workstation and goes through review, as on the demo.
- **Verifying the database certificate:** connections use `sslmode=require`, which encrypts without checking the certificate. Adding the RDS CA bundle to the image would allow `verify-full`.
- **Container hardening:** this is not tested yet, including read-only root filesystems.
- **Multi-region, VPC flow logs and GuardDuty:** these are account-level choices for Cover.
