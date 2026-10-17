# Production setup on AWS (item 25). Written to be reviewed and applied by Cover; nothing here has been applied.
# State lives in an S3 bucket you create first: terraform init -backend-config=backend.hcl (see README.md).
terraform {
  required_version = ">= 1.11" # write-only arguments keep the database password out of state

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
  }

  backend "s3" {}
}

locals {
  name = "regengine-${var.environment}"
  tags = {
    project     = "cover-regulatory"
    environment = var.environment
  }
}

provider "aws" {
  region = var.region
  default_tags { tags = local.tags }
}

# CloudFront certificates and the CloudFront WAF must live in us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags { tags = local.tags }
}
