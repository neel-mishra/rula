variable "aws_region" {
  default = "us-east-1"
}

variable "environment" {
  description = "dev | staging | prod"
  type        = string
}

variable "app_name" {
  default = "inbox-chief-of-staff"
}

variable "vpc_cidr" {
  default = "10.0.0.0/16"
}

variable "db_instance_class" {
  default = "db.t3.medium"
}

variable "redis_node_type" {
  default = "cache.t3.micro"
}

variable "ecr_api_repo" {
  description = "ECR repo URI for API image"
  type        = string
  default     = ""
}

variable "ecr_worker_repo" {
  description = "ECR repo URI for worker image"
  type        = string
  default     = ""
}

variable "image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}
