output "distribution_domain" {
  description = "The CloudFront hostname — verify the page and certificate here before touching DNS."
  value       = aws_cloudfront_distribution.page.domain_name
}

output "dns_records" {
  description = "Records to create when manage_dns = false: certificate validation plus the page alias target."
  value = var.manage_dns ? null : {
    validation = [
      for option in aws_acm_certificate.page.domain_validation_options : {
        name  = option.resource_record_name
        type  = option.resource_record_type
        value = option.resource_record_value
      }
    ]
    alias_target = aws_cloudfront_distribution.page.domain_name
  }
}

output "bucket" {
  description = "The page bucket name."
  value       = aws_s3_bucket.page.bucket
}

output "function_name" {
  description = "The renderer Lambda's name, for manual invocation and log tailing."
  value       = aws_lambda_function.renderer.function_name
}
