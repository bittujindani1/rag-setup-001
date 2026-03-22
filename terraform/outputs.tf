output "documents_bucket" {
  value = aws_s3_bucket.documents.bucket
}

output "vectors_bucket" {
  value = aws_s3_bucket.vectors.bucket
}

output "extracted_bucket" {
  value = aws_s3_bucket.extracted.bucket
}

output "analytics_bucket" {
  value = aws_s3_bucket.analytics.bucket
}

output "analytics_glue_database" {
  value = aws_glue_catalog_database.analytics.name
}

output "frontend_bucket" {
  value = aws_s3_bucket.frontend.bucket
}

output "ecr_repository_url" {
  value = aws_ecr_repository.rag_api.repository_url
}

output "frontend_url" {
  value = aws_s3_bucket_website_configuration.frontend.website_endpoint
}

output "lambda_function_url" {
  value = aws_lambda_function_url.rag_api.function_url
}
