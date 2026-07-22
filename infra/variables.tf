variable "region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-2"
}

variable "bucket_name" {
  description = "Name of the existing data-lake bucket, created by hand and imported."
  type        = string
  default     = "phoms-data-lake"
}
