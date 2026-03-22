from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
import traceback

from rag_logic import answer_from_youtube

load_dotenv()

app = FastAPI(title="YouTube RAG Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    youtube_url: str
    question: str
    chat_history: list | None = None


@app.post("/ask")
def ask_question(req: QueryRequest):
    try:
        result = answer_from_youtube(
            youtube_url=req.youtube_url,
            question=req.question,
            chat_history=req.chat_history
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Show real error in response for debugging
        error_detail = traceback.format_exc()
        print("INTERNAL ERROR:", error_detail)
        raise HTTPException(status_code=500, detail=str(e))