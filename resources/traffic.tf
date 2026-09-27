# Background traffic: invokes each Lambda once a minute so CloudWatch always has data.
# Use project/traffic.py for bursts right before the demo.

resource "aws_cloudwatch_event_rule" "traffic" {
  name                = "tfpulse-demo-traffic"
  schedule_expression = "rate(1 minute)"
}

locals {
  traffic_targets = {
    catalog  = aws_lambda_function.catalog
    orders   = aws_lambda_function.orders
    checkout = aws_lambda_function.checkout
  }
}

resource "aws_cloudwatch_event_target" "traffic" {
  for_each = local.traffic_targets
  rule     = aws_cloudwatch_event_rule.traffic.name
  arn      = each.value.arn
}

resource "aws_lambda_permission" "traffic" {
  for_each      = local.traffic_targets
  statement_id  = "AllowEventBridgeTraffic"
  action        = "lambda:InvokeFunction"
  function_name = each.value.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.traffic.arn
}
