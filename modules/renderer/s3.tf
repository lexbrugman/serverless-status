# Objects are written by the Lambda, never by OpenTofu.
resource "aws_s3_bucket" "page" {
  bucket = var.domain
}

resource "aws_s3_bucket_public_access_block" "page" {
  bucket = aws_s3_bucket.page.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "page" {
  bucket = aws_s3_bucket.page.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

data "aws_iam_policy_document" "page_bucket" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.page.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.page.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "page" {
  bucket = aws_s3_bucket.page.id
  policy = data.aws_iam_policy_document.page_bucket.json
}
