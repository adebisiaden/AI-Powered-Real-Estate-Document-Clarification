provider "google" {
  project = var.project_id
  region  = var.region
}




  
    
  

  
    
resource "google_storage_bucket" "artifact_tracking_mlflow_artifact" {
  name          = var.artifact_bucket
  location      = var.region
  force_destroy = true

  labels = {
    component  = "mlflow-artifacts"
    managed-by = "terraform"
    stage      = "artifact_tracking"
  }
}
    
  

  
    
  

  
    
  

  
    
  

  
    
  





# Detect if any stage needs PostgreSQL for mlflow or feast

module "cloud_sql_postgres" {
  source = "./modules/cloud_sql_postgres"
  project_id      = var.project_id
  region          = var.region
  db_instance_name = "mlflow-postgres-deploy-ml-lab"
  db_name         = "mlflow"
  db_user         = "mlflow"
  # Create the metrics DB when Grafana is in the stack so it has a backend to connect to
  create_metrics_db = true
}







  
    
module "experiment_tracking_mlflow" {
  source = "./modules/mlflow/cloud/gcp/cloud_run"
  count  = var.enable_experiment_tracking_mlflow && var.experiment_tracking_mlflow_service_name != "" ? 1 : 0
  project_id = var.project_id
  region     = var.region
  create_service = true
  allow_public_access = var.allow_public_access
  cpu_limit = var.cpu_limit
  memory_limit = var.memory_limit
  cpu_request = var.cpu_request
  memory_request = var.memory_request
  max_scale = var.max_scale
  container_concurrency = var.container_concurrency
  artifact_bucket = var.artifact_bucket
  
  backend_store_uri = module.cloud_sql_postgres.connection_string
  cloudsql_instance_annotation = module.cloud_sql_postgres.instance_connection_name
  
  use_postgres = true
  
  depends_on = [module.cloud_sql_postgres]
  
  
      # Skip - handled separately below
    
  
      image = var.experiment_tracking_mlflow_image != "" ? var.experiment_tracking_mlflow_image : var.global_image
    
  
  
  service_name = var.experiment_tracking_mlflow_service_name
  
}
    
  

  
    
module "artifact_tracking_mlflow" {
  source = "./modules/mlflow/cloud/gcp/cloud_run"
  count  = var.enable_artifact_tracking_mlflow ? 1 : 0
  project_id = var.project_id
  region     = var.region
  create_service = false
  allow_public_access = var.allow_public_access
  cpu_limit = var.cpu_limit
  memory_limit = var.memory_limit
  cpu_request = var.cpu_request
  memory_request = var.memory_request
  max_scale = var.max_scale
  container_concurrency = var.container_concurrency
  artifact_bucket = google_storage_bucket.artifact_tracking_mlflow_artifact.name
  
  backend_store_uri = module.cloud_sql_postgres.connection_string
  cloudsql_instance_annotation = module.cloud_sql_postgres.instance_connection_name
  
  use_postgres = true
  
  depends_on = [module.cloud_sql_postgres]
  
  
      # Skip - already handled above
    
  
  
      image = var.artifact_tracking_mlflow_image != "" ? var.artifact_tracking_mlflow_image : var.global_image
    
  
  
}
    
  

  
    
module "model_registry_mlflow" {
  source = "./modules/mlflow/cloud/gcp/cloud_run"
  count  = var.enable_model_registry_mlflow ? 1 : 0
  project_id = var.project_id
  region     = var.region
  create_service = false
  allow_public_access = var.allow_public_access
  cpu_limit = var.cpu_limit
  memory_limit = var.memory_limit
  cpu_request = var.cpu_request
  memory_request = var.memory_request
  max_scale = var.max_scale
  container_concurrency = var.container_concurrency
  artifact_bucket = var.artifact_bucket
  
  backend_store_uri = module.cloud_sql_postgres.connection_string
  cloudsql_instance_annotation = module.cloud_sql_postgres.instance_connection_name
  
  use_postgres = true
  
  depends_on = [module.cloud_sql_postgres]
  
  
  
      image = var.model_registry_mlflow_image != "" ? var.model_registry_mlflow_image : var.global_image
    
  
  
}
    
  

  
    
  

  
    
  

  
    
  


# Optional: FastAPI model serving module, only if present in stack

  
    
  

  
    
  

  
    
  

  
    
module "model_serving_fastapi" {
  source              = "./modules/fastapi/cloud/gcp/cloud_run"
  count               = var.enable_model_serving_fastapi && var.model_serving_fastapi_service_name != "" ? 1 : 0
  project_id          = var.project_id
  region              = var.region
  service_name        = var.model_serving_fastapi_service_name
  image               = var.model_serving_fastapi_image
  mlflow_tracking_uri = (
    length(module.experiment_tracking_mlflow) > 0 ?
    module.experiment_tracking_mlflow[0].service_url : ""
  )
  mlflow_artifact_bucket = (
    length(module.experiment_tracking_mlflow) > 0 ?
    module.experiment_tracking_mlflow[0].bucket_name : var.artifact_bucket
  )
  model_uri           = var.model_uri
  cpu_limit           = var.cpu_limit
  memory_limit        = var.memory_limit
  allow_public_access = var.allow_public_access
  
  backend_store_uri   = module.cloud_sql_postgres.connection_string
  # IMPORTANT: Provide a dedicated metrics database connection for the app
  # so prediction metrics are not written to the MLflow database.
  db_connection_string = module.cloud_sql_postgres.metrics_connection_string_cloud_sql
  use_postgres        = true
  cloudsql_instance_annotation = module.cloud_sql_postgres.instance_connection_name
  
  # Feast connection - check if feast exists in stack
  
  
    
      
    
  
    
      
    
  
    
      
    
  
    
      
    
  
    
      
    
  
    
      
    
  
  feast_service_url = ""
  enable_feast_connection = false
  bigquery_dataset = "mlops"
  
}
    
  

  
    
  

  
    
  


# Optional: Feast feature store module, only if present in stack

  
    
  

  
    
  

  
    
  

  
    
  

  
    
  

  
    
  


# Workflow orchestration for multiple cron jobs (offline_scoring, drift_monitoring)

  
    
  

  
    
  

  
    
  

  
    
  

  
    
  

  
    
  



# Optional: Grafana monitoring module, only if present in stack

  
    
  

  
    
  

  
    
  

  
    
  

  
    
module "model_monitoring_grafana" {
  source              = "./modules/grafana/cloud/gcp/cloud_run"
  count               = var.enable_model_monitoring_grafana && var.model_monitoring_grafana_service_name != "" ? 1 : 0
  project_id          = var.project_id
  region              = var.region
  service_name        = var.model_monitoring_grafana_service_name
  image               = var.model_monitoring_grafana_image
  cpu_limit           = var.cpu_limit
  memory_limit        = var.memory_limit
  allow_public_access = var.allow_public_access
  
  metrics_connection_string = module.cloud_sql_postgres.grafana_connection_string_cloud_sql
  use_metrics_database = true
  cloudsql_instance_annotation = module.cloud_sql_postgres.instance_connection_name
  depends_on = [module.cloud_sql_postgres]
  
}
    
  

  
    
  

module "bigquery" {
  source     = "./modules/bigquery/cloud/gcp"
  project_id = var.project_id
  region     = var.region
  dataset_id = "mlops"
}



# MLflow — single URL and bucket regardless of how many stack stages use it


  
    
      
      
    
  

  
    
  

  
    
  

  
    
  

  
    
  

  
    
  


output "mlflow_url" {
  value = var.enable_experiment_tracking_mlflow && length(module.experiment_tracking_mlflow) > 0 ? module.experiment_tracking_mlflow[0].service_url : ""
}
output "artifact_bucket" {
  value = var.enable_experiment_tracking_mlflow && length(module.experiment_tracking_mlflow) > 0 ? module.experiment_tracking_mlflow[0].bucket_name : ""
}


output "postgresql_credentials" {
  value = module.cloud_sql_postgres.postgresql_credentials
  sensitive = true
}

output "bigquery_dataset" {
  value = module.bigquery.dataset_id
}


  
    
    
    
  

  
    
    
    
  

  
    
    
    
  

  
    
output "fastapi_url" {
  value = length(module.model_serving_fastapi) > 0 ? module.model_serving_fastapi[0].service_url : ""
}
    
    
    
  

  
    
    
output "grafana_url" {
  value = length(module.model_monitoring_grafana) > 0 ? module.model_monitoring_grafana[0].service_url : ""
}
    
    
  

  
    
    
    
  


# Output for Workflow orchestration (cron jobs) if present

  
    
  

  
    
  

  
    
  

  
    
  

  
    
  

  
    
  





 