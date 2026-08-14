# The metrics-read credentials flow from the checks module straight into
# SSM — never through GitHub, a file, or a shell.
resource "aws_ssm_parameter" "prometheus" {
  name  = local.prometheus_parameter
  type  = "SecureString"
  value = jsonencode(var.prometheus)
}
