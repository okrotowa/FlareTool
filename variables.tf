variable "region" {
  type    = string
  default = "eu-central-1"
}

variable "state_bucket" {
  description = "Name of the state bucket (bootstrap output), used for the monitor read-only policy."
  type        = string
}

variable "alert_email" {
  description = "Email for the monthly budget alert. Leave empty to skip the budget."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  type    = number
  default = 5
}
