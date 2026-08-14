# Core terraform ruleset only, recommended preset. No provider plugin: it
# would add a network download to every lint run, and the AWS-specific rules
# it carries mostly duplicate what `tofu validate` and the module tests
# already prove for a stack this size.
plugin "terraform" {
  enabled = true
  preset  = "recommended"
}
