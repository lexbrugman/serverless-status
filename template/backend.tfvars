# Yours: where the state lives. A backend block cannot read variables, so
# this file is passed explicitly: tofu init -backend-config=backend.tfvars
# The bucket must match instance.auto.tfvars and bootstrap/terraform.tfvars.
bucket       = "CHANGE-ME-state-bucket"
key          = "serverless-status.tfstate"
region       = "eu-west-1"
use_lockfile = true
