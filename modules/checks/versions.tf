terraform {
  required_version = ">= 1.10"

  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = ">= 4.0"
      # cloud: stack lookup and access policies. sm: probes and checks. Both
      # are configured in the root — the sm credentials come out of the
      # root's grafana_synthetic_monitoring_installation, which this module
      # cannot own without a provider-configuration cycle.
      configuration_aliases = [grafana.cloud, grafana.sm]
    }
  }
}
