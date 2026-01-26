from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

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
        # if isinstance(result, dict) and result.get("status"):
        #     return result
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
