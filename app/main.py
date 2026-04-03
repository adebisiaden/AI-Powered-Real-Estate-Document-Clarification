from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List

app = FastAPI()

# ----------------------------
# Toy "model"
# ----------------------------
class ToyModel:
    def __init__(self):
        self.weights = [0.5, 1.0, -0.2]
        self.bias = 1.0

    def predict(self, features: List[float]) -> float:
        return sum(w * x for w, x in zip(self.weights, features)) + self.bias


model = ToyModel()


# ----------------------------
# Schemas (Pydantic)
# ----------------------------
class PredictionRequest(BaseModel):
    features: List[float]


class PredictionResponse(BaseModel):
    prediction: float
    model_loaded: bool


# ----------------------------
# Endpoints
# ----------------------------
@app.get("/")
def read_root():
    return {"message": "Welcome!"}


@app.get("/health")
def health_check():
    return {
        "status": "ok" if model is not None else "error",
        "model_loaded": model is not None
    }


@app.post("/predict", response_model=PredictionResponse)
def predict(data: PredictionRequest):
    if model is None:
        raise HTTPException(status_code=500, detail="Model is not loaded")

    pred = model.predict(data.features)

    return PredictionResponse(
        prediction=pred,
        model_loaded=True
    )