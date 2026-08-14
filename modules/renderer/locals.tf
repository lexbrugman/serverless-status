locals {
  # One derivation for every resource name, so the domain names the stack.
  name = replace(var.domain, ".", "-")

  prometheus_parameter = "/${var.domain}/prometheus"
}
