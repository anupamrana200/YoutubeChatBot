import os
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import PromptTemplate
from pinecone import Pinecone, ServerlessSpec
from langchain_pinecone import PineconeVectorStore
from langchain_core.documents import Document
from urllib.parse import urlparse, parse_qs



# Extract video ID
# -----------------------
def extract_video_id(youtube_url: str):
    parsed_url = urlparse(youtube_url)

    if parsed_url.hostname in ("www.youtube.com", "youtube.com"):
        return parse_qs(parsed_url.query).get("v", [None])[0]

    if parsed_url.hostname == "youtu.be":
        return parsed_url.path.lstrip("/")

    return None

#Find the summary intent, if the user needs to summarize the video without clicking on the summarize button.
SUMMARY_INTENTS = [
    "summarize",
    "summary",
    "summarise",
    "give me a summary",
    "summarize the video",
    "summarise the video",
    "explain the video briefly",
    "short summary",
    "video summary",
    "I want to summarize the video",
    "Please provide me summarize version of the video"
]

def is_summary_intent(question: str) -> bool:
    q = question.lower().strip()
    return any(intent in q for intent in SUMMARY_INTENTS)



# One-time setup
# -----------------------
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0
)

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index_name = "youtube-chatbot"

if index_name not in pc.list_indexes().names():
    pc.create_index(
        name=index_name,
        dimension=1536,
        metric="cosine",
        spec=ServerlessSpec(
            cloud="aws",
            region="us-east-1"
        )
    )

def format_timestamp(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"

def format_chat_history(chat_history):
    if not chat_history:
        return ""

    lines = []
    for msg in chat_history:
        role = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role}: {msg['text']}")

    return "\n".join(lines)



# Core RAG function
# -----------------------

def answer_from_youtube(youtube_url: str, question: str, chat_history=None):

    # Normalize summary intent
    if is_summary_intent(question):
        question = "__SUMMARY__"

    video_id = extract_video_id(youtube_url)
    if not video_id:
        raise ValueError("Invalid YouTube URL")

    # Fetch transcript
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.fetch(video_id, languages=["en"])

        documents = []
        for item in transcript_list:
            documents.append(
                Document(
                    page_content=item.text,
                    metadata={
                        "start": item.start,
                        "duration": item.duration
                    }
                )
            )

        if not documents:
            raise ValueError("Empty transcript")

    except (TranscriptsDisabled, NoTranscriptFound):
        return {
            "status": "NO_ENGLISH_TRANSCRIPT",
            "message": (
                "This video does not have an English transcript. "
                "Please play a video which has english transcript, then ask me questions."
            )
        }

    

    # SUMMARY MODE
    if question == "__SUMMARY__":

        summary_blocks = []

        for doc in documents:
            start = doc.metadata.get("start")
            duration = doc.metadata.get("duration")
            end = start + duration

            start_ts = format_timestamp(start)
            end_ts = format_timestamp(end)

            summary_blocks.append(
                f"[{start_ts} – {end_ts}] {doc.page_content}"
            )

        summary_context = "\n".join(summary_blocks)

        summary_prompt = f"""
            You are a helpful assistant.

            Summarize the following YouTube video transcript clearly and concisely.

            Rules:
            - Use ONLY the provided transcript.
            - Do NOT add external information.
            - Organize the summary by main topics.
            - Include relevant timestamps in the summary where helpful.

            Transcript:
            {summary_context}
        """

        summary = llm.invoke(summary_prompt)

        return {
            "video_id": video_id,
            "question": "Summarize this video",
            "answer": summary.content
        }





    # Split transcript
    # splitter = RecursiveCharacterTextSplitter(
    #     chunk_size=1000,
    #     chunk_overlap=200
    # )
    # chunks = splitter.create_documents([transcript])

    # Pinecone ingestion guard (CRITICAL FIX)
    index = pc.Index(index_name)
    stats = index.describe_index_stats()

    if video_id not in stats.get("namespaces", {}):
        PineconeVectorStore.from_documents(
            documents=documents,
            embedding=embeddings,
            index_name=index_name,
            namespace=video_id
        )


    # Vector store (retrieval only)
    vector_store = PineconeVectorStore(
        index_name=index_name,
        embedding=embeddings,
        namespace=video_id
    )

    retriever = vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 4}
    )

    # 5. Retrieval
    docs = retriever.invoke(question)
    # context_text = "\n\n".join(doc.page_content for doc in docs)

    context_blocks = []

    for doc in docs:
        start = doc.metadata.get("start")
        duration = doc.metadata.get("duration")
        end = start + duration

        start_ts = format_timestamp(start)
        end_ts = format_timestamp(end)

        context_blocks.append(
            f"[{start_ts} - {end_ts}] {doc.page_content}"
        )

    context_text = "\n".join(context_blocks)


    conversation_context = format_chat_history(chat_history)

    final_prompt = f"""
        You are a helpful assistant. Who is able to read the youtube transcript and answer the questions of the user.

        Answer the question using the transcript and the conversation done so far below.

        Rules: 
        If the answer is based on the transcript:
        - Mention the relevant timestamp(s).

        If the transcript does NOT contain enough information:
        - Do NOT include timestamps.
        - Answer using general knowledge.

        conversation so far: 
        {conversation_context}

        Context:
        {context_text}

        Question:
        {question}
    """

    answer = llm.invoke(final_prompt)

    return {
        "video_id": video_id,
        "question": question,
        "answer": answer.content
    }
