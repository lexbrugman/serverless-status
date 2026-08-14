resource "aws_cloudfront_origin_access_control" "page" {
  name                              = local.name
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# The managed CachingOptimized policy honors the origin's Cache-Control.
# Every object carries max-age=30, so the edge refreshes itself within one
# render cycle and no invalidation is ever issued.
data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

resource "aws_cloudfront_distribution" "page" {
  enabled             = true
  comment             = var.domain
  aliases             = [var.domain]
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  is_ipv6_enabled     = true

  origin {
    origin_id                = "page-bucket"
    domain_name              = aws_s3_bucket.page.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.page.id
  }

  default_cache_behavior {
    target_origin_id       = "page-bucket"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_optimized.id
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.page.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }
}
