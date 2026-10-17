#!/usr/bin/env bash
# Guardrail check, run before every commit in addition to gitleaks.
# 1. Prints every staged line matching the guardrail keyword grep, for human review.
# 2. Blocks the commit when a matching line also assigns a literal that looks like a credential.
set -euo pipefail
keywords='api[_-]?key|secret|token|passw|Bearer |sk-'
added=$(git diff --cached -U0 -- . ':(exclude)scripts/check-staged-secrets.sh' | grep -E '^\+[^+]' || true)
review=$(echo "$added" | grep -iE "$keywords" || true)
if [[ -n "$review" ]]; then
  echo "Keyword matches in staged changes (review):" >&2
  echo "$review" | cut -c1-100 >&2
fi
# keyword on the left of an assignment, and a value of 16+ chars containing a digit; or an sk- key that is not
# the end of a word (so "task-definition" is not one)
literal='(api[_-]?key|secret|token|passw)[A-Za-z0-9_]*["'"'"']?[[:space:]]*[=:][[:space:]]*["'"'"']?[A-Za-z0-9_/+.=-]*[0-9][A-Za-z0-9_/+.=-]{12,}|(^|[^A-Za-z])sk-[A-Za-z0-9_-]{10,}|Bearer [A-Za-z0-9._-]{10,}'
block=$(echo "$review" | grep -E "$literal" | grep -viE 'replace-me|change-me|placeholder|\$\{|os\.environ|getenv|settings\.|SecretStr' || true)
if [[ -n "$block" ]]; then
  echo "Blocked: staged line looks like a credential value:" >&2
  echo "$block" | cut -c1-60 | sed 's/$/.../' >&2
  exit 1
fi
