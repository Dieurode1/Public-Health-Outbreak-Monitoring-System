# PHOMS infrastructure — the AWS resources the pipeline runs on, as code.
#
# Single source of truth for the data lake bucket and the IAM identity the
# extractors use to write to it. The bucket was created by hand on 2026-07-22
# and imported into this configuration, so this file is authoritative from here.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
  # Credentials come from the environment (~/.aws/credentials), never from here.
}
