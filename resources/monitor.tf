# Read-only permissions the MCP server needs. Attach this policy to the IAM user
# or role you (and teammates) use at the hackathon. No write access to anything.

resource "aws_iam_policy" "monitor_readonly" {
  name        = "flare-demo-monitor-readonly"
  description = "Read Terraform state, CloudWatch metrics and logs for the flare demo"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadState"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:GetObjectVersion"]
        Resource = "arn:aws:s3:::${var.state_bucket}/*"
      },
      {
        Sid      = "ListStateVersions"
        Effect   = "Allow"
        Action   = ["s3:ListBucket", "s3:ListBucketVersions"]
        Resource = "arn:aws:s3:::${var.state_bucket}"
      },
      {
        Sid      = "ReadMetrics"
        Effect   = "Allow"
        Action   = ["cloudwatch:GetMetricData", "cloudwatch:GetMetricStatistics", "cloudwatch:ListMetrics"]
        Resource = "*"
      },
      {
        Sid    = "ReadLogs"
        Effect = "Allow"
        Action = [
          "logs:FilterLogEvents", "logs:GetLogEvents", "logs:DescribeLogGroups",
          "logs:DescribeLogStreams", "logs:StartQuery", "logs:GetQueryResults"
        ]
        Resource = "*"
      },
      {
        Sid      = "ReadLambdaConfig"
        Effect   = "Allow"
        Action   = ["lambda:GetFunctionConfiguration", "lambda:ListFunctions"]
        Resource = "*"
      }
    ]
  })
}

# Cost guardrail: email alert when forecasted monthly spend passes 80% of the budget.
resource "aws_budgets_budget" "demo" {
  count        = var.alert_email == "" ? 0 : 1
  name         = "flare-demo-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}

output "monitor_policy_arn" {
  value = aws_iam_policy.monitor_readonly.arn
}

output "function_names" {
  value = [for f in local.traffic_targets : f.function_name]
}
