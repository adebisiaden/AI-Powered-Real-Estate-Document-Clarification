# AI-Powered-Real-Estate-Document-Clarification
This project aims to develop an AI-powered platform that simplifies complex real estate litigation. By processing lease agreements and legal documents, the software translates dense jargon into plain language and proactively flags unfavorable terms or hidden risks.


# Running the API Locally (without Docker)
1. Install dependencies
pip install -r requirements.txt
2. Run the FastAPI server
uvicorn app.main:app --reload --port 8000
3. Open in browser
http://127.0.0.1:8000/docs


# Running with Docker
1. Build the Docker image
docker build -t fastapi-toy-model .
2. Run the container
docker run -p 8000:8000 fastapi-toy-model
3. Open in browser
http://127.0.0.1:8000/docs


# Example Request: /predict
Input
{
  "features": [1.0, 2.0, 3.0]
}

Output
{
  "prediction": 2.9,
  "model_loaded": true
}