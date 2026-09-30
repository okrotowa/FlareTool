# Three small Lambdas for the demo:
#   catalog  - fast and healthy
#   orders   - healthy, with a rare realistic error (~0.5%)
#   checkout - takes 0.8-1.5 s; healthy with timeout = 10, red when broken to timeout = 1

resource "aws_iam_role" "lambda_exec" {
  name = "flare-demo-lambda-exec"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ---------- catalog ----------

data "archive_file" "catalog" {
  type        = "zip"
  source_file = "${path.module}/../project/catalog.py"
  output_path = "${path.module}/build/catalog.zip"
}

resource "aws_cloudwatch_log_group" "catalog" {
  name              = "/aws/lambda/flare-demo-catalog"
  retention_in_days = 3
}

resource "aws_lambda_function" "catalog" {
  function_name    = "flare-demo-catalog"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "catalog.handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  filename         = data.archive_file.catalog.output_path
  source_code_hash = data.archive_file.catalog.output_base64sha256
  memory_size      = 128
  timeout          = 5
  depends_on       = [aws_cloudwatch_log_group.catalog, aws_iam_role_policy_attachment.lambda_logs]
}

# ---------- orders ----------

data "archive_file" "orders" {
  type        = "zip"
  source_file = "${path.module}/../project/orders.py"
  output_path = "${path.module}/build/orders.zip"
}

resource "aws_cloudwatch_log_group" "orders" {
  name              = "/aws/lambda/flare-demo-orders"
  retention_in_days = 3
}

resource "aws_lambda_function" "orders" {
  function_name    = "flare-demo-orders"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "orders.handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  filename         = data.archive_file.orders.output_path
  source_code_hash = data.archive_file.orders.output_base64sha256
  memory_size      = 128
  timeout          = 5
  depends_on       = [aws_cloudwatch_log_group.orders, aws_iam_role_policy_attachment.lambda_logs]
}

# ---------- checkout (the one we break on stage) ----------

data "archive_file" "checkout" {
  type        = "zip"
  source_file = "${path.module}/../project/checkout.py"
  output_path = "${path.module}/build/checkout.zip"
}

resource "aws_cloudwatch_log_group" "checkout" {
  name              = "/aws/lambda/flare-demo-checkout"
  retention_in_days = 3
}

resource "aws_lambda_function" "checkout" {
  function_name    = "flare-demo-checkout"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "checkout.handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  filename         = data.archive_file.checkout.output_path
  source_code_hash = data.archive_file.checkout.output_base64sha256
  memory_size      = 128
  timeout          = 1
  depends_on       = [aws_cloudwatch_log_group.checkout, aws_iam_role_policy_attachment.lambda_logs]
}
