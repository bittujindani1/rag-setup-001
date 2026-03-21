terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region                      = var.aws_region
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

locals {
  prefix = var.project_name
  lambda_image_uri = var.lambda_image_uri != "" ? var.lambda_image_uri : "${aws_ecr_repository.rag_api.repository_url}:${var.lambda_image_tag}"
}

resource "aws_s3_bucket" "documents" {
  bucket = "${local.prefix}-documents"
}

resource "aws_ecr_repository" "rag_api" {
  name                 = var.ecr_repository_name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_s3_bucket_cors_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "POST", "PUT"]
    allowed_origins = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

resource "aws_s3_bucket" "frontend" {
  bucket = "${local.prefix}-frontend"
}

resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "index.html"
  }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

data "aws_iam_policy_document" "frontend_public_read" {
  statement {
    effect = "Allow"
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]
  }
}

resource "aws_s3_bucket_policy" "frontend_public_read" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_public_read.json
}

resource "aws_s3_bucket" "vectors" {
  bucket = "${local.prefix}-vectors"
}

resource "aws_s3_bucket" "extracted" {
  bucket = "${local.prefix}-extracted"
}

resource "aws_dynamodb_table" "chat_history" {
  name         = "rag_chat_history"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "session_id"
  range_key    = "timestamp"

  attribute {
    name = "session_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "N"
  }
}

resource "aws_dynamodb_table" "query_cache" {
  name         = "rag_query_cache"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "query_hash"

  attribute {
    name = "query_hash"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

resource "aws_dynamodb_table" "doc_store" {
  name         = "rag_doc_store"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "doc_id"

  attribute {
    name = "doc_id"
    type = "S"
  }
}

resource "aws_dynamodb_table" "filename_index" {
  name         = "rag_filename_index"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "index_filename"

  attribute {
    name = "index_filename"
    type = "S"
  }
}

resource "aws_dynamodb_table" "rate_limits" {
  name         = "rag_rate_limits"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "session_id"
  range_key    = "request_id"

  attribute {
    name = "session_id"
    type = "S"
  }

  attribute {
    name = "request_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

resource "aws_dynamodb_table" "chat_threads" {
  name         = "rag_chat_threads"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "thread_id"
  range_key    = "timestamp"

  attribute {
    name = "thread_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }
}

resource "aws_dynamodb_table" "document_categories" {
  name         = "rag_document_categories"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "index_filename"

  attribute {
    name = "index_filename"
    type = "S"
  }

  attribute {
    name = "index_name"
    type = "S"
  }

  global_secondary_index {
    name            = "index_name-index"
    hash_key        = "index_name"
    projection_type = "ALL"
  }
}

resource "aws_dynamodb_table" "ingest_jobs" {
  name         = "rag_ingest_jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "job_id"

  attribute {
    name = "job_id"
    type = "S"
  }
}

resource "aws_dynamodb_table" "feedback" {
  name         = "rag_user_feedback"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "created_at"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "N"
  }
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "rag_lambda_role" {
  name               = "${local.prefix}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "rag_lambda_policy" {
  statement {
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["*"]
  }

  statement {
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:BatchWriteItem",
    ]
    resources = [
      aws_dynamodb_table.chat_history.arn,
      aws_dynamodb_table.query_cache.arn,
      aws_dynamodb_table.doc_store.arn,
      aws_dynamodb_table.filename_index.arn,
      aws_dynamodb_table.rate_limits.arn,
      aws_dynamodb_table.chat_threads.arn,
      aws_dynamodb_table.document_categories.arn,
      "${aws_dynamodb_table.document_categories.arn}/index/*",
      aws_dynamodb_table.ingest_jobs.arn,
      aws_dynamodb_table.feedback.arn,
    ]
  }

  statement {
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.documents.arn,
      "${aws_s3_bucket.documents.arn}/*",
      aws_s3_bucket.vectors.arn,
      "${aws_s3_bucket.vectors.arn}/*",
      aws_s3_bucket.extracted.arn,
      "${aws_s3_bucket.extracted.arn}/*",
    ]
  }

  statement {
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "rag_lambda_policy" {
  name   = "${local.prefix}-lambda-policy"
  role   = aws_iam_role.rag_lambda_role.id
  policy = data.aws_iam_policy_document.rag_lambda_policy.json
}

resource "aws_lambda_function" "rag_api" {
  function_name = "${local.prefix}-rag-api"
  role          = aws_iam_role.rag_lambda_role.arn
  package_type  = "Image"
  image_uri     = local.lambda_image_uri
  timeout       = 900
  memory_size   = 2048

  environment {
    variables = {
      AWS_REGION                         = var.aws_region
      VECTOR_STORE                       = "s3"
      DOC_STORE                          = "dynamodb"
      CHAT_HISTORY_STORE                 = "dynamodb"
      CACHE_STORE                        = "dynamodb"
      LLM_PROVIDER                       = "bedrock"
      BEDROCK_FALLBACK_MODEL             = "anthropic.claude-3-sonnet-20240229-v1:0"
      S3_BUCKET_DOCUMENTS                = aws_s3_bucket.documents.bucket
      S3_BUCKET_VECTORS                  = aws_s3_bucket.vectors.bucket
      S3_BUCKET_EXTRACTED                = aws_s3_bucket.extracted.bucket
      DYNAMODB_CHAT_HISTORY_TABLE        = aws_dynamodb_table.chat_history.name
      DYNAMODB_QUERY_CACHE_TABLE         = aws_dynamodb_table.query_cache.name
      DYNAMODB_DOC_STORE_TABLE           = aws_dynamodb_table.doc_store.name
      DYNAMODB_FILENAME_INDEX_TABLE      = aws_dynamodb_table.filename_index.name
      DYNAMODB_RATE_LIMIT_TABLE          = aws_dynamodb_table.rate_limits.name
      DYNAMODB_THREAD_TABLE              = aws_dynamodb_table.chat_threads.name
      DYNAMODB_DOCUMENT_CATEGORIES_TABLE = aws_dynamodb_table.document_categories.name
      DYNAMODB_INGEST_JOBS_TABLE         = aws_dynamodb_table.ingest_jobs.name
      DYNAMODB_FEEDBACK_TABLE            = aws_dynamodb_table.feedback.name
      RATE_LIMIT_REQUESTS_PER_MINUTE     = "15"
    }
  }
}

resource "aws_lambda_function_url" "rag_api" {
  function_name      = aws_lambda_function.rag_api.function_name
  authorization_type = "NONE"

  cors {
    allow_credentials = false
    allow_headers     = ["*"]
    allow_methods     = ["*"]
    allow_origins     = ["*"]
    expose_headers    = ["*"]
    max_age           = 3600
  }
}

resource "aws_lambda_permission" "allow_function_url" {
  statement_id           = "AllowPublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.rag_api.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}
