# The accounts feeding this page. Adding an org is: an entry here, its
# token in TF_VAR_grafana_cloud_tokens, and one copy of the per-org block
# in providers.tf and main.tf. Removing one is the reverse; its checks then
# fail the plan until they are reassigned or deleted.
orgs = {
  example = {
    stack_slug = "examplecorp"
  }
}
