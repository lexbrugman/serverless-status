# The renderer module's plan-time behavior: the manifest seam, the pinned
# runtime configuration, and input validation — offline via mocked providers.

# Mock defaults exist because the provider validates known values at plan
# time: policy documents must be JSON, certificate references must be ARNs.
mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }

  mock_resource "aws_lambda_function" {
    defaults = {
      arn = "arn:aws:lambda:eu-west-1:123456789012:function:mock"
    }
  }

  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::123456789012:role/mock"
    }
  }
}

mock_provider "aws" {
  alias = "us_east_1"

  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-1:123456789012:certificate/mock"
      domain_validation_options = [
        {
          domain_name           = "status.example.com"
          resource_record_name  = "_mock.status.example.com."
          resource_record_type  = "CNAME"
          resource_record_value = "_mock.acm-validations.aws."
        },
      ]
    }
  }

}

mock_provider "archive" {}

variables {
  domain        = "status.example.com"
  dns_zone_name = "example.com"

  site = {
    name     = "Example Corp"
    timezone = "Europe/Amsterdam"
  }

  page = {}

  prometheus_sources = [
    {
      query_url   = "https://prometheus-prod-01-eu-west-0.grafana.net/api/prom"
      user        = "987654"
      token       = "glc_mock"
      write_token = "glc_mock_write"
    },
  ]

  check_manifests = [
    {
      schema_version = 4
      checks = {
        website = {
          display           = "Website"
          group             = "Web"
          type              = "https"
          host              = "www.example.com"
          port              = 443
          path              = "/"
          order             = 10
          latency_budget_ms = null
          frequency_minutes = 5
        }
      }
    },
  ]
}

run "configuration" {
  command = plan

  assert {
    condition     = aws_lambda_function.renderer.runtime == "python3.14"
    error_message = "the runtime mirrors LAMBDA_PYTHON_VERSION in versions.env"
  }

  assert {
    condition     = aws_lambda_function.renderer.reserved_concurrent_executions == 1
    error_message = "runs must never overlap"
  }

  assert {
    condition     = aws_cloudwatch_log_group.lambda.retention_in_days == 14
    error_message = "the log group must expire — Lambda must not own an unbounded one"
  }

  assert {
    condition     = aws_dynamodb_table.history.billing_mode == "PROVISIONED"
    error_message = "on-demand does not qualify for the always-free capacity"
  }

  assert {
    condition     = [for t in aws_dynamodb_table.history.ttl : t.attribute_name][0] == "expires_at"
    error_message = "retention is TTL-driven"
  }

  assert {
    condition     = aws_scheduler_schedule.render.schedule_expression == "rate(1 minute)"
    error_message = "the page renders every minute"
  }

  assert {
    condition     = aws_ssm_parameter.prometheus.type == "SecureString"
    error_message = "credentials are stored encrypted"
  }

  assert {
    condition     = length(aws_route53_record.alias) == 2
    error_message = "managed DNS creates both A and AAAA aliases"
  }
}

run "mismatched_manifest_schema_fails_the_plan" {
  command = plan

  variables {
    check_manifests = [
      {
        schema_version = 1
        checks         = {}
      },
    ]
  }

  expect_failures = [terraform_data.manifest_compatibility]
}

run "colliding_check_keys_fail_the_plan" {
  command = plan

  variables {
    check_manifests = [
      { schema_version = 4, checks = { website = { group = "Web", order = 10 } } },
      { schema_version = 4, checks = { website = { group = "Web", order = 10 } } },
    ]
  }

  expect_failures = [terraform_data.manifest_compatibility]
}

run "rejects_malformed_accent" {
  command = plan

  variables {
    site = {
      name     = "Example Corp"
      timezone = "Europe/Amsterdam"
      accent   = "green"
    }
  }

  expect_failures = [var.site]
}

run "rejects_empty_timezone" {
  command = plan

  variables {
    site = {
      name     = "Example Corp"
      timezone = ""
    }
  }

  expect_failures = [var.site]
}

run "rejects_history_beyond_retention" {
  command = plan

  variables {
    page = {
      history_days   = 400
      retention_days = 90
    }
  }

  expect_failures = [var.page]
}

run "rejects_outage_log_beyond_retention" {
  command = plan

  variables {
    page = {
      outage_log_days = 500
    }
  }

  expect_failures = [var.page]
}

run "rejects_malformed_domain" {
  command = plan

  variables {
    domain = "https://status.example.com"
  }

  expect_failures = [var.domain]
}
