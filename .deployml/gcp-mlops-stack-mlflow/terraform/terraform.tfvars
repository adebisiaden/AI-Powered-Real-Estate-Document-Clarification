project_id = "deploy-ml-lab"
region = "us-west1"
zone = "us-west1-a"
global_image = "gcr.io/deploy-ml-lab/mlflow/mlflow:latest"
allow_public_access = true
auto_approve = false

# Cloud Run specific defaults
cpu_limit = "2000m"
memory_limit = "2Gi"
cpu_request = "1000m"
memory_request = "1Gi"
max_scale = 10
container_concurrency = 80

# Database defaults
db_type = "postgresql" 
db_user = "mlflow"      # Set to match cloud_sql_postgres module
db_password = ""        # Auto-generated
db_name = "mlflow"      # Set to match cloud_sql_postgres module
db_port = "5432"        

# Output backend_store_uri only once (global)


  
    
  

  
    
  

  
    
      
    
  

  
    
  

  
    
  

  
    
  




  
    
      
experiment_tracking_mlflow_service_name = "mlflow-server"
      
    
      
experiment_tracking_mlflow_image = "us-west1-docker.pkg.dev/deploy-ml-lab/mlops-images/mlflow:latest"
      
    
  

  
    
      
artifact_bucket = "mlflow-artifacts-deploy-ml-lab"
      
    
      
use_postgres = "False"
      
    
      
artifact_tracking_mlflow_image = "us-west1-docker.pkg.dev/deploy-ml-lab/mlops-images/mlflow:latest"
      
    
  

  
    
      
    
      
model_registry_mlflow_image = "us-west1-docker.pkg.dev/deploy-ml-lab/mlops-images/mlflow:latest"
      
    
  

  
    
      
model_serving_fastapi_service_name = "fastapi-mlflow-server"
      
    
      
model_serving_fastapi_image = "us-west1-docker.pkg.dev/deploy-ml-lab/mlops-images/fastapi:latest"
      
    
  

  
    
      
model_monitoring_grafana_service_name = "grafana-server"
      
    
      
model_monitoring_grafana_image = "us-west1-docker.pkg.dev/deploy-ml-lab/mlops-images/grafana-container:latest"
      
    
  

  
    
  


create_artifact_bucket = true

# Enable/disable modules based on YAML configuration

  
enable_experiment_tracking_mlflow = true
  

  
enable_artifact_tracking_mlflow = true
  

  
enable_model_registry_mlflow = true
  

  
enable_model_serving_fastapi = true
  

  
enable_model_monitoring_grafana = true
  

  
enable_cloud_sql_postgres_cloud_sql_postgres = true
  


# Feast-specific configuration
feast_bigquery_dataset = "feast_offline_store"
feast_create_bigquery_dataset = true 