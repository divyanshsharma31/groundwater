from fastapi import FastAPI, Query, HTTPException
import pandas as pd
import joblib
import numpy as np
import json
import os
from rapidfuzz import fuzz
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Groundwater Prototype API", version="2.0")

# --- Enable CORS for frontend ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Helper function ---
def _clean(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower()

# --- Load Data (using correct paths from backend directory) ---
rainfall = pd.read_csv("../data/rainfall.csv")
rainfall["state_name"] = _clean(rainfall["state_name"])
rainfall["year_month"] = rainfall["year_month"].astype(str)

groundwater = pd.read_csv("../data/groundwater.csv")
groundwater["state_name"] = _clean(groundwater["state_name"])
groundwater["district_name"] = _clean(groundwater["district_name"])
groundwater["year_month"] = groundwater["year_month"].astype(str)

# --- Load trained model ---
model = joblib.load("../models/groundwater_predictor.pkl")

# --- Load user credentials for fuzzy login ---
with open("users.json") as f:
    USERS = json.load(f)

def fuzzy_login(input_user: str, input_pass: str, threshold: int = 85) -> bool:
    """
    Check login using fuzzy string matching.
    Returns True if both username and password are close enough.
    """
    for stored_user, stored_pass in USERS.items():
        user_score = fuzz.ratio(input_user, stored_user)
        pass_score = fuzz.ratio(input_pass, stored_pass)

        if user_score >= threshold and pass_score >= threshold:
            return True
    return False

# --- API Routes ---
@app.get("/")
def root():
    return {"status": "ok", "message": "Groundwater Backend API is running"}

# --- Authentication ---
@app.get("/api/login")
def login(username: str = Query(...), password: str = Query(...)):
    if fuzzy_login(username, password):
        return {"status": "success", "message": "Login granted"}
    raise HTTPException(status_code=401, detail="Invalid credentials")

# --- Data Endpoints ---
@app.get("/api/months")
def get_months():
    return sorted(rainfall["year_month"].unique().tolist())

@app.get("/api/states")
def get_states():
    return sorted(rainfall["state_name"].unique().tolist())

@app.get("/api/districts")
def get_districts(state: str = Query(...)):
    df = groundwater[groundwater["state_name"] == state]
    return sorted(df["district_name"].dropna().unique().tolist())

@app.get("/api/timeseries/state")
def state_timeseries(state: str = Query(...)):
    r = rainfall[rainfall["state_name"] == state]
    g = groundwater[groundwater["state_name"] == state].groupby(
        ["state_name", "year_month"], as_index=False
    )["gw_level_m_bgl"].mean()
    merged = pd.merge(r, g, on=["state_name", "year_month"], how="outer").sort_values("year_month")
    return merged.fillna(0).to_dict(orient="records")

# --- Prediction Endpoint ---
@app.get("/api/predict")
def predict(
    state: str = Query(...),
    year_month: str = Query(...),
    rainfall_value: float = Query(..., description="Rainfall in mm"),
    lag_gw: float = Query(..., description="Lag groundwater level (m bgl)")
):
    X = np.array([[rainfall_value, lag_gw]])
    pred = model.predict(X)[0]

    return {
        "state": state,
        "year_month": year_month,
        "rainfall_mm": rainfall_value,
        "lag_gw": lag_gw,
        "predicted_groundwater_level": round(float(pred), 2)
    }
