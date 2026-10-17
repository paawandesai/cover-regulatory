#!/usr/bin/env bash
# Build and ship one commit: push the images, migrate, roll the API, publish the web app.
#   infra/aws/deploy.sh            (deploys HEAD; the working tree must be clean)
# Needs: aws CLI signed in to the target account, docker, node 22, terraform initialised with backend.hcl.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
cd "$here"

[ -z "$(git -C "$root" status --porcelain)" ] || { echo "commit or stash changes first" >&2; exit 1; }
tag=$(git -C "$root" rev-parse --short=12 HEAD)
region=$(terraform output -raw region)
api_repo=$(terraform output -raw api_repository)
dbtool_repo=$(terraform output -raw dbtool_repository)

aws ecr get-login-password --region "$region" | docker login --username AWS --password-stdin "${api_repo%%/*}"
docker build --platform linux/amd64 -t "$api_repo:$tag" "$root/backend"
docker push "$api_repo:$tag"
docker build --platform linux/amd64 -f "$root/deploy/dbtool.Dockerfile" -t "$dbtool_repo:latest-build" "$root/deploy"
docker push "$dbtool_repo:latest-build"

# Migrations first, with the new image; they only add, so the old API keeps working meanwhile.
terraform apply -input=false -var "api_image_tag=$tag" -target='aws_ecs_task_definition.job["migrate"]'
./run-task.sh migrate

# Everything else, including the API service, which rolls one task at a time and rolls back if new tasks fail
# their health check.
terraform apply -input=false -var "api_image_tag=$tag"
aws ecs wait services-stable --region "$region" --cluster "$(terraform output -raw cluster)" \
  --services "$(terraform output -raw api_service)"

(cd "$root/frontend" && npm ci --no-audit --no-fund && npx vite build)
bucket=$(terraform output -raw web_bucket)
# Hashed assets are cached for a year; index.html is revalidated on every load.
aws s3 sync "$root/frontend/dist" "s3://$bucket" --delete --exclude index.html \
  --cache-control "public, max-age=31536000, immutable"
aws s3 cp "$root/frontend/dist/index.html" "s3://$bucket/index.html" --cache-control "no-cache"
aws cloudfront create-invalidation --distribution-id "$(terraform output -raw distribution_id)" \
  --paths /index.html > /dev/null

curl -fsS "$(terraform output -raw url)/api/health" | jq '{status, approved_rules, pending_rules, chunks}'
echo "deployed $tag"
