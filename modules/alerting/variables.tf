variable "name" {
  description = "Stack slug, used to name what this module creates inside the stack."
  type        = string
}

variable "jobs" {
  description = "Checks to alert on: the Prometheus job label, which is the check key, and how often it runs. The frequency is what sizes the window a verdict is made over, so it travels with the job rather than being assumed."
  type = list(object({
    key               = string
    frequency_minutes = number
  }))
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
