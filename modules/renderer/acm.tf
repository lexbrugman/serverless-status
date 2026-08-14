# CloudFront only accepts certificates from us-east-1, hence the aliased
# provider. The validation resource blocks the apply until issuance, so a
# finished apply is a working TLS endpoint.
resource "aws_acm_certificate" "page" {
  provider = aws.us_east_1

  domain_name       = var.domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_acm_certificate_validation" "page" {
  provider = aws.us_east_1

  certificate_arn = aws_acm_certificate.page.arn
  validation_record_fqdns = var.manage_dns ? [
    for record in aws_route53_record.validation : record.fqdn
  ] : null
}
