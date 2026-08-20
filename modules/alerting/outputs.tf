output "contact_point" {
  description = "Name of the contact point the rules route to — where a failing check is announced."
  value       = grafana_contact_point.operators.name
}

output "alerting_jobs" {
  description = "What each rule covers, for eyeballing against the page: the checks a failure pages about, and every check watched for going quiet."
  value = {
    down      = sort([for job in var.down_jobs : job.key])
    reporting = sort([for job in var.reporting_jobs : job.key])
  }
}
