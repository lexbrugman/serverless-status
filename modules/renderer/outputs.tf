output "distribution_domain" {
  description = "The CloudFront hostname — verify the page and certificate here before touching DNS."
  value       = aws_cloudfront_distribution.page.domain_name
}

output "bucket" {
  description = "The page bucket name."
  value       = aws_s3_bucket.page.bucket
}

output "function_name" {
  description = "The renderer Lambda's name, for manual invocation and log tailing."
  value       = aws_lambda_function.renderer.function_name
}
