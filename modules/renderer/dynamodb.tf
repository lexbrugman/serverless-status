# Provisioned, not on-demand: PAY_PER_REQUEST does not qualify for the
# always-free capacity. 5/5 units dwarf the actual load (~9 queries and a
# handful of writes per minute).
resource "aws_dynamodb_table" "history" {
  name         = local.name
  billing_mode = "PROVISIONED"

  read_capacity  = 5
  write_capacity = 5

  hash_key  = "PK"
  range_key = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  # DynamoDB deletes expired rollups and outages in the background: no cron,
  # no cleanup Lambda, no consumed write capacity.
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  # Point-in-time recovery stays off: it costs money and the data is
  # reconstructible from Grafana's 13-month retention.
  deletion_protection_enabled = true
}
