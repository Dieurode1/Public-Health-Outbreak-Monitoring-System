# The data lake. Created by hand 2026-07-22, imported into Terraform so this
# file is the source of truth going forward. Raw snapshots land under
# raw/{source}/{pull_date}/ and are never overwritten (ADR 5); versioning is a
# second safety net at the storage layer.

resource "aws_s3_bucket" "lake" {
  bucket = var.bucket_name

  tags = {
    Project   = "phoms"
    ManagedBy = "terraform"
  }
}

resource "aws_s3_bucket_versioning" "lake" {
  bucket = aws_s3_bucket.lake.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "lake" {
  bucket                  = aws_s3_bucket.lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}
