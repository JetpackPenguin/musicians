# main.py
"""
Musicians RESTful API Service
===============================
FastAPI + Supabase 
Methods: GET, POST, PUT, PATCH, DELETE
"""

import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import create_client, Client

# ---------------------------------------------------------------------------
# Environment & Supabase Init
# ---------------------------------------------------------------------------
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not all([SUPABASE_URL, SUPABASE_ANON_KEY]):
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_ANON_KEY in .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Musicians API",
    description="RESTful service for managing musicians",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class MusicianCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, example="Jimi Hendrix")
    genre: str = Field(..., min_length=1, max_length=100, example="Rock")
    country: str = Field(..., min_length=1, max_length=100, example="USA")
    bio: str = Field(default="", max_length=2000, example="Legendary guitarist.")
    avatar_url: Optional[str] = Field(default="", example="https://example.com/jimi.jpg")


class MusicianPut(BaseModel):
    """Used for PUT requests (replacing the entire record)."""
    name: str = Field(..., min_length=1, max_length=200)
    genre: str = Field(..., min_length=1, max_length=100)
    country: str = Field(..., min_length=1, max_length=100)
    bio: str = Field(default="", max_length=2000)
    avatar_url: str = Field(default="")


class MusicianPatch(BaseModel):
    """Used for PATCH requests (partially updating a record)."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    genre: Optional[str] = Field(default=None, min_length=1, max_length=100)
    country: Optional[str] = Field(default=None, min_length=1, max_length=100)
    bio: Optional[str] = Field(default=None, max_length=2000)
    avatar_url: Optional[str] = Field(default=None)


class MusicianResponse(BaseModel):
    id: int
    name: str
    genre: str
    country: str
    bio: str
    avatar_url: str
    created_at: str


class MusicianListResponse(BaseModel):
    total: int
    musicians: list[MusicianResponse]


class MessageResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_response(row: dict) -> MusicianResponse:
    """Convert a database row dict to a MusicianResponse."""
    return MusicianResponse(**row)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

# ── GET /musicians — List all musicians ──────────

@app.get("/musicians", response_model=MusicianListResponse)
def list_musicians(
    genre: Optional[str] = Query(default=None, description="Filter by genre"),
    search: Optional[str] = Query(default=None, description="Search in name or bio"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    query = supabase.table("musicians").select("*", count="exact")

    if genre:
        query = query.eq("genre", genre)
    if search:
        query = query.or_(f"name.ilike.%{search}%,bio.ilike.%{search}%")

    query = query.order("id", desc=False).range(offset, offset + limit - 1)
    response = query.execute()

    return MusicianListResponse(
        total=response.count if response.count is not None else 0,
        musicians=[_row_to_response(r) for r in response.data],
    )


# ── GET /musicians/{id} — Get a single musician by ID ───────────────────

@app.get("/musicians/{musician_id}", response_model=MusicianResponse)
def get_musician(musician_id: int):
    response = supabase.table("musicians").select("*").eq("id", musician_id).execute()

    if not response.data:
        raise HTTPException(status_code=404, detail="Musician not found")

    return _row_to_response(response.data[0])


# ── POST /musicians — Create a new musician ─────────────────

@app.post("/musicians", response_model=MusicianResponse, status_code=201)
def create_musician(payload: MusicianCreate):
    response = supabase.table("musicians").insert(payload.model_dump()).execute()

    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create musician")

    return _row_to_response(response.data[0])


# ── PUT /musicians/{id} — Replace a musician ──────────────────────

@app.put("/musicians/{musician_id}", response_model=MusicianResponse)
def replace_musician(musician_id: int, payload: MusicianPut):
    """
    PUT replaces the entire musician record. 
    Any optional fields omitted will be reset to their defaults (empty strings).
    """
    check = supabase.table("musicians").select("id").eq("id", musician_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Musician not found")

    update_data = payload.model_dump()
    
    response = supabase.table("musicians").update(update_data).eq("id", musician_id).execute()

    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to replace musician")

    return _row_to_response(response.data[0])


# ── PATCH /musicians/{id} — Partially update a musician ──────────────────────

@app.patch("/musicians/{musician_id}", response_model=MusicianResponse)
def partially_update_musician(musician_id: int, payload: MusicianPatch):
    """
    PATCH updates only the fields provided in the request body.
    Existing data for omitted fields will remain unchanged in the DB.
    """
    check = supabase.table("musicians").select("id").eq("id", musician_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Musician not found")

    # exclude_unset=True ensures we only send fields the user explicitly included
    update_data = payload.model_dump(exclude_unset=True)
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    response = supabase.table("musicians").update(update_data).eq("id", musician_id).execute()

    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to update musician")

    return _row_to_response(response.data[0])


# ── DELETE /musicians/{id} — Delete a musician ──────────────────────────

@app.delete("/musicians/{musician_id}", response_model=MessageResponse)
def delete_musician(musician_id: int):
    check = supabase.table("musicians").select("id").eq("id", musician_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Musician not found")

    supabase.table("musicians").delete().eq("id", musician_id).execute()

    return MessageResponse(message="Musician deleted successfully")


# ── Health check ───────────────────────────────────────────────────────────

@app.get("/health", response_model=MessageResponse)
def health_check():
    return MessageResponse(message="Musicians API is running")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
