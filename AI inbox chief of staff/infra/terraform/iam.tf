# ── IAM — least privilege roles per ECS task ─────────────────────────────────

# API task role
resource "aws_iam_role" "api_task" {
  name = "${local.name_prefix}-api-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "api_task" {
  name = "${local.name_prefix}-api-task-policy"
  role = aws_iam_role.api_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SQSSend"
        Effect = "Allow"
        Action = ["sqs:SendMessage", "sqs:GetQueueAttributes"]
        Resource = [for q in aws_sqs_queue.main : q.arn]
      },
      {
        Sid    = "SecretsRead"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = ["arn:aws:secretsmanager:${var.aws_region}:*:secret:${local.name_prefix}/*"]
      },
      {
        Sid    = "KMSDecrypt"
        Effect = "Allow"
        Action = ["kms:Decrypt", "kms:GenerateDataKey"]
        Resource = [aws_kms_key.rds.arn]
      }
    ]
  })
}

# Worker task role
resource "aws_iam_role" "worker_task" {
  name = "${local.name_prefix}-worker-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "worker_task" {
  name = "${local.name_prefix}-worker-task-policy"
  role = aws_iam_role.worker_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SQSConsumeAll"
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:ChangeMessageVisibility"
        ]
        Resource = concat(
          [for q in aws_sqs_queue.main : q.arn],
          [for q in aws_sqs_queue.dlq : q.arn]
        )
      },
      {
        Sid    = "SecretsRead"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = ["arn:aws:secretsmanager:${var.aws_region}:*:secret:${local.name_prefix}/*"]
      },
      {
        Sid    = "KMSAll"
        Effect = "Allow"
        Action = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
        Resource = [aws_kms_key.rds.arn]
      },
      {
        Sid    = "S3AuditWrite"
        Effect = "Allow"
        Action = ["s3:PutObject"]
        Resource = ["arn:aws:s3:::${local.name_prefix}-audit-*/*"]
      }
    ]
  })
}

# GitHub Actions OIDC deploy role (no static AWS keys in CI)
resource "aws_iam_role" "github_deploy" {
  name = "${local.name_prefix}-github-deploy"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:*:ref:refs/heads/main"
        }
      }
    }]
  })
}

data "aws_caller_identity" "current" {}
