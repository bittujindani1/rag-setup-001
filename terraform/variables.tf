variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "project_name" {
  type    = string
  default = "rag-serverless"
}

variable "lambda_image_uri" {
  type    = string
  default = ""
}

variable "lambda_image_tag" {
  type    = string
  default = "latest"
}

variable "ecr_repository_name" {
  type    = string
  default = "rag-api"
}
