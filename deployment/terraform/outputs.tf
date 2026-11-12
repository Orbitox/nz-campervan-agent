output "artifact_bucket_url" {
  description = "GCS bucket URI for Vertex AI Agent Runtime staging artifacts."
  value       = google_storage_bucket.agent_runtime_artifacts.url
}

output "agent_service_account_email" {
  description = "Least-privilege service account email for KiwiCamp Agent Runtime."
  value       = google_service_account.agent_runtime_sa.email
}

output "telemetry_bigquery_dataset_id" {
  description = "BigQuery dataset receiving Intent vs. Outcome structured audit logs."
  value       = google_bigquery_dataset.agent_telemetry.dataset_id
}
