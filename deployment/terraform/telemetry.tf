# BigQuery Dataset & Log Sink for AgentOps Intent/Outcome Audit Analytics
resource "google_bigquery_dataset" "agent_telemetry" {
  dataset_id  = "kiwicamp_agentops_telemetry"
  location    = var.region
  description = "Stores structured JSON Intent/Outcome audit logs and OpenTelemetry traces for KiwiCamp."
  project     = var.project_id

  depends_on = [google_project_service.enabled_apis]
}

resource "google_logging_project_sink" "intent_outcome_audit_sink" {
  name        = "kiwicamp-intent-outcome-bigquery-sink"
  destination = "bigquery.googleapis.com/projects/${var.project_id}/datasets/${google_bigquery_dataset.agent_telemetry.dataset_id}"
  filter      = "jsonPayload.service=\"kiwicamp-nz-campervan-agent\" AND (jsonPayload.audit_phase=\"INTENT\" OR jsonPayload.audit_phase=\"OUTCOME\")"

  unique_writer_identity = true
}

resource "google_bigquery_dataset_iam_member" "sink_bq_writer" {
  dataset_id = google_bigquery_dataset.agent_telemetry.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = google_logging_project_sink.intent_outcome_audit_sink.writer_identity
  project    = var.project_id
}
