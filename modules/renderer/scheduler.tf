resource "aws_scheduler_schedule" "render" {
  name = local.name

  schedule_expression = "rate(1 minute)"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.renderer.arn
    role_arn = aws_iam_role.scheduler.arn
  }
}
