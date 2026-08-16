output "contact_point" {
  description = "Name of the contact point the rules route to — where a failing check is announced."
  value       = grafana_contact_point.operators.name
}

output "alerting_jobs" {
  description = "The check identities this rule covers, for eyeballing against the page."
  value       = var.jobs
}
