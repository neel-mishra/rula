# ── SQS Queues — per pipeline with Dead Letter Queues ────────────────────────

locals {
  queues = ["ingest", "triage", "draft", "brief", "memory", "eval"]
}

resource "aws_sqs_queue" "dlq" {
  for_each = toset(local.queues)
  name     = "${local.name_prefix}-${each.key}-dlq"

  # 14-day retention on DLQ for replay analysis
  message_retention_seconds = 1209600
  kms_master_key_id         = "alias/aws/sqs"
}

resource "aws_sqs_queue" "main" {
  for_each = toset(local.queues)
  name     = "${local.name_prefix}-${each.key}"

  # Visibility timeout: 5 min (longer than max worker processing time)
  visibility_timeout_seconds = 300
  message_retention_seconds  = 86400  # 24h
  kms_master_key_id          = "alias/aws/sqs"

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = 3  # 3 retries before DLQ
  })

  tags = {
    Pipeline = each.key
  }
}

output "sqs_queue_urls" {
  value = { for k, q in aws_sqs_queue.main : k => q.url }
}
