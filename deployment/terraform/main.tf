terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.38"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.38"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

locals {
  required_apis = [
    "aiplatform.googleapis.com",
    "secretmanager.googleapis.com",
    "dlp.googleapis.com",
    "cloudtrace.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "bigquery.googleapis.com",
    "discoveryengine.googleapis.com",
    "storage.googleapis.com",
  ]
}

resource "google_project_service" "enabled_apis" {
  for_each           = toset(local.required_apis)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# Staging & Artifact GCS Bucket for Vertex AI Agent Runtime (ReasoningEngine)
resource "google_storage_bucket" "agent_runtime_artifacts" {
  name                        = "${var.project_id}-${var.agent_name}-artifacts"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = true
  }

  depends_on = [google_project_service.enabled_apis]
}

# Secret Manager Secrets (Criterion 5.3: Zero hardcoded API keys)
resource "google_secret_manager_secret" "managed_secrets" {
  for_each  = toset(var.secret_ids)
  secret_id = each.value
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled_apis]
}
