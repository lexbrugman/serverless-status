# The deployment artifact is a zip built at plan time: the handler code plus
# the manifest baked in as a file. Baking the manifest into the package —
# rather than an environment variable — sidesteps Lambda's 4 KB env limit,
# which an inlined logo_svg would blow through.
data "archive_file" "lambda" {
  type        = "zip"
  output_path = "${path.module}/.archive/lambda.zip"

  dynamic "source" {
    for_each = fileset("${path.module}/src", "*.py")
    content {
      filename = source.value
      content  = file("${path.module}/src/${source.value}")
    }
  }

  source {
    filename = "manifest.json"
    content  = jsonencode(var.page_manifest)
  }
}

# Created explicitly so Lambda cannot create an unmanaged, never-expiring
# log group on first invocation.
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "renderer" {
  function_name = local.name
  role          = aws_iam_role.lambda.arn

  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  # The runtime mirrors LAMBDA_PYTHON_VERSION in versions.env, asserted by
  # scripts/check-cross-layer.py.
  runtime = "python3.14"
  handler = "handler.render_handler"

  memory_size = 512
  timeout     = 60

  # Runs never overlap: a slow render must delay the next one, not race it.
  reserved_concurrent_executions = 1

  environment {
    variables = merge(
      {
        TABLE_NAME  = aws_dynamodb_table.history.name
        BUCKET_NAME = aws_s3_bucket.page.bucket
        PROM_PARAM  = aws_ssm_parameter.prometheus.name
      },
      var.page_version == null ? {} : { PAGE_VERSION = var.page_version },
    )
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}
