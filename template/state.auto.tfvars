# Yours: where the state lives — each fact stated exactly once. The key
# names match the S3 backend's arguments so this one file serves three
# consumers: `tofu init -backend-config=state.auto.tfvars`, the root's
# auto-loaded variables, and the bootstrap root via
# `-var-file=../state.auto.tfvars`.
bucket = "CHANGE-ME-state-bucket"
region = "eu-west-1"
