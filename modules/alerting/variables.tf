variable "down_jobs" {
  description = "Checks to alert on when they fail: the Prometheus job label, which is the check key, and how often it runs. The frequency is what sizes the window a verdict is made over, so it travels with the job rather than being assumed. A check with alert: false is absent here."
  type = list(object({
    key               = string
    frequency_minutes = number
  }))
}

variable "reporting_jobs" {
  description = "Every check the renderer reports on, including those that opted out of down-alerting. Opting out says a failure of the thing is not worth a page; it does not say a failure of the monitoring is, and a check nobody is running is the second. The display name and target travel with the key because Grafana knows only the job label, and a notification naming a slug tells its reader less than the page they would have to open anyway."
  type = list(object({
    key     = string
    display = string
    target  = string
  }))

  validation {
    condition     = length(var.reporting_jobs) > 0
    error_message = "alerting needs at least one check to watch."
  }
}

variable "page_url" {
  description = "Where the status page is served. A notification points at it rather than restating what it holds: the page stamps an outage at the sample it began, while Grafana can only know when its own window filled, so any duration stated here would contradict the record."
  type        = string
}

variable "prometheus" {
  description = "Where the probe results live, from the checks module: query URL, user, and read token. The token reaches the stack as a datasource credential and never a file."
  type = object({
    query_url = string
    user      = string
    token     = string
  })
  sensitive = true
}

variable "email_addresses" {
  description = "Who hears about a failing check."
  type        = list(string)
}

variable "down_window_multiple" {
  description = "How many probe intervals the verdict is made over. Counted in executions rather than wall-clock minutes: a pending period shorter than the probe interval only delays the page, it never requires a second failure."
  type        = number

  validation {
    condition     = var.down_window_multiple >= 2
    error_message = "down_window_multiple must be at least 2 — a window of one probe interval cannot require a second failure, which is the whole point of it."
  }
}

variable "down_quorum" {
  description = "The share of probe executions in the window that must have succeeded for a check to count as up. Below 1 it also absorbs a single unhappy probe location, which is why Grafana recommends running alerting checks from several."
  type        = number

  validation {
    condition     = var.down_quorum > 0 && var.down_quorum <= 1
    error_message = "down_quorum is a share of probe executions, so it lies in (0, 1]."
  }
}
