# Dedicated Least-Privilege Service Account for the KiwiCamp Agent Runtime
resource "google_service_account" "agent_runtime_sa" {
  account_id   = "kiwicamp-agent-runtime-sa"
  display_name = "KiwiCamp Vertex AI Agent Runtime Service Account"
  project      = var.project_id
}

locals {
  agent_iam_roles = [
    "roles/aiplatform.user",
    "roles/secretmanager.secretAccessor",
    "roles/dlp.user",
    "roles/cloudtrace.agent",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/discoveryengine.viewer",
    "roles/storage.objectAdmin",
  ]
}

resource "google_project_iam_member" "agent_runtime_permissions" {
  for_each = toset(local.agent_iam_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.agent_runtime_sa.email}"
}
