# The pipeline's own identity — the credentials the extractors authenticate as.
#
# Deliberately minimal: it can put, get, and list objects in the data lake and
# nothing else. It cannot manage the bucket, touch other buckets, or do anything
# in IAM. If these credentials leak, the blast radius is one bucket's objects.
#
# This is the least-privilege artifact — a reviewer reads it to see exactly what
# the running pipeline is trusted to do.

resource "aws_iam_user" "pipeline" {
  name = "phoms-pipeline"
  tags = {
    Project   = "phoms"
    ManagedBy = "terraform"
  }
}

data "aws_iam_policy_document" "pipeline" {
  statement {
    sid    = "ReadWriteObjects"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
    ]
    resources = ["${aws_s3_bucket.lake.arn}/*"]
  }

  statement {
    sid    = "ListTheBucket"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
    ]
    resources = [aws_s3_bucket.lake.arn]
  }
}

resource "aws_iam_user_policy" "pipeline" {
  name   = "phoms-pipeline-s3"
  user   = aws_iam_user.pipeline.name
  policy = data.aws_iam_policy_document.pipeline.json
}

resource "aws_iam_access_key" "pipeline" {
  user = aws_iam_user.pipeline.name
}

output "pipeline_access_key_id" {
  value = aws_iam_access_key.pipeline.id
}

output "pipeline_secret_access_key" {
  value     = aws_iam_access_key.pipeline.secret
  sensitive = true
}