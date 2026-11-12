variable "project_id" {
  description = "Google Cloud Project ID hosting the KiwiCamp Vertex AI Agent Runtime."
  type        = string
}

variable "region" {
  description = "Primary Google Cloud region for Vertex AI Agent Engine and GCS buckets."
  type        = string
  default     = "us-central1"
}

variable "agent_name" {
  description = "Canonical deployment name for the KiwiCamp ReasoningEngine agent."
  type        = string
  default     = "kiwicamp-nz-campervan-agent"
}

variable "secret_ids" {
  description = "List of Secret Manager secret identifiers provisioned for external tool APIs."
  type        = list(string)
  default = [
    "nz-doc-api-key",
    "cook-strait-ferry-api-key",
    "nz-metservice-api-key",
    "youtube-data-api-key",
  ]
}
