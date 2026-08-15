# The zone predates this module and is looked up, never created: destroying
# this stack must never be able to take down the zone.
data "aws_route53_zone" "page" {
  count = var.manage_dns ? 1 : 0

  name = var.dns_zone_name
}

locals {
  validation_options = {
    for option in aws_acm_certificate.page.domain_validation_options :
    option.domain_name => option
  }
}

# Keyed by var.domain, never by the certificate's computed attributes: an
# import expands every resource without planning the certificate, so
# computed keys would make the whole graph unresolvable there.
resource "aws_route53_record" "validation" {
  for_each = var.manage_dns ? toset([var.domain]) : toset([])

  zone_id = data.aws_route53_zone.page[0].zone_id
  name    = local.validation_options[each.value].resource_record_name
  type    = local.validation_options[each.value].resource_record_type
  ttl     = 300
  records = [local.validation_options[each.value].resource_record_value]
}

resource "aws_route53_record" "alias" {
  for_each = var.manage_dns ? toset(["A", "AAAA"]) : toset([])

  zone_id = data.aws_route53_zone.page[0].zone_id
  name    = var.domain
  type    = each.value

  alias {
    name                   = aws_cloudfront_distribution.page.domain_name
    zone_id                = aws_cloudfront_distribution.page.hosted_zone_id
    evaluate_target_health = false
  }
}
