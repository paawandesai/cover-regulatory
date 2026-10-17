#!/usr/bin/env bash
# Run one of the job tasks (migrate, purge, refresh, restore) once, wait for it, and fail if it failed.
#   infra/aws/run-task.sh migrate
#   infra/aws/run-task.sh restore DUMP_KEY=dumps/regengine-2026-10-17.dump
set -euo pipefail
cd "$(dirname "$0")"
job=${1:?usage: run-task.sh <migrate|purge|refresh|restore> [NAME=value ...]}
shift

out() { terraform output -raw "$1"; }
region=$(out region)
cluster=$(out cluster)
family=$(terraform output -json job_families | jq -r --arg j "$job" '.[$j] // empty')
[ -n "$family" ] || { echo "unknown job: $job" >&2; exit 2; }
subnets=$(terraform output -json private_subnets | jq -r 'join(",")')
sg=$(out tasks_security_group)

overrides='{"containerOverrides":[]}'
if [ $# -gt 0 ]; then
  env=$(printf '%s\n' "$@" | jq -R 'split("=") | {name: .[0], value: (.[1:] | join("="))}' | jq -s .)
  overrides=$(jq -n --arg c "$job" --argjson e "$env" '{containerOverrides: [{name: $c, environment: $e}]}')
fi

task=$(aws ecs run-task --region "$region" --cluster "$cluster" --task-definition "$family" --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$subnets],securityGroups=[$sg],assignPublicIp=DISABLED}" \
  --overrides "$overrides" --query 'tasks[0].taskArn' --output text)
echo "started $job: ${task##*/}"
aws ecs wait tasks-stopped --region "$region" --cluster "$cluster" --tasks "$task"
code=$(aws ecs describe-tasks --region "$region" --cluster "$cluster" --tasks "$task" \
  --query 'tasks[0].containers[0].exitCode' --output text)
echo "$job exited with $code (logs: /$(terraform output -raw cluster)/app in CloudWatch)"
[ "$code" = "0" ]
