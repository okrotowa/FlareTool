# tfpulse demo stack

Demo infrastructure for the hackathon: three Lambdas deployed with Terraform, state in a
versioned S3 bucket, background traffic so CloudWatch always has data. This is the
environment the tool monitors; the tool itself gets built at the event.

Region: `eu-central-1` (Frankfurt). Requires Terraform >= 1.16 and Python 3 with `boto3`.

## 1. Create the state bucket (once)

```bash
cd bootstrap
terraform init
terraform apply
# note the `state_bucket` output
```

## 2. Deploy the stack

```bash
cd ../stack
# put the bucket name into versions.tf (backend block) and terraform.tfvars
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```

Then attach the `monitor_policy_arn` output to the IAM user or role you'll use at the
hackathon, and confirm the budget-alert email AWS sends you.

## 3. Let it run

EventBridge invokes each Lambda once a minute, so by the event you'll have days of
history. For a quick burst (e.g. right after a deploy):

```bash
python ../scripts/traffic.py --count 100
```

Expected: `catalog` and `checkout` all ok, `orders` with a rare error.

## 4. The "break" for the demo

In `stack/lambdas.tf`, change the checkout function's timeout:

```hcl
  timeout          = 10   # ->   timeout = 1
```

Commit it on a branch (`demo/break-checkout`), apply it ~10 minutes before the pitch, and
run a burst so the errors show up in CloudWatch:

```bash
terraform apply
python ../scripts/traffic.py --only checkout --count 100
```

Checkout now fails most calls with `Task timed out after 1.00 seconds`. The fix on stage
is setting it back to `10`.

## 5. Tear down after the hackathon

```bash
cd stack && terraform destroy
cd ../bootstrap && terraform destroy
```

## Expected cost

Effectively $0 within Lambda's always-free allowance; well under $1/month even without
it. The biggest risk is forgetting to tear down, so the budget alert emails you at 80% of
$5 forecasted spend.
