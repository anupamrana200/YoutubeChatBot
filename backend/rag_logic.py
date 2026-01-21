import os
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import PromptTemplate
from pinecone import Pinecone, ServerlessSpec
from langchain_pinecone import PineconeVectorStore
from langchain_core.documents import Document
from urllib.parse import urlparse, parse_qs


# -----------------------
# Extract video ID
# -----------------------
def extract_video_id(youtube_url: str):
    parsed_url = urlparse(youtube_url)

    if parsed_url.hostname in ("www.youtube.com", "youtube.com"):
        return parse_qs(parsed_url.query).get("v", [None])[0]

    if parsed_url.hostname == "youtu.be":
        return parsed_url.path.lstrip("/")

    return None


# -----------------------
# One-time setup
# -----------------------
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0
)

prompt = PromptTemplate(
    template="""
    You are a helpful assistant.

    Answer the question using the transcript context below.

    If the answer is based on the transcript:
    - Mention the relevant timestamp(s).

    If the transcript does NOT contain enough information:
    - Do NOT include timestamps.
    - Say clearly: "This answer is not based on the video transcript." after writing this answer using general knowledge.

    Context:
    {context}

    Question:
    {question}
    """,
    input_variables=["context", "question"]
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


# -----------------------
# Core RAG function
# -----------------------
def answer_from_youtube(youtube_url: str, question: str):

    video_id = extract_video_id(youtube_url)
    if not video_id:
        raise ValueError("Invalid YouTube URL")

    # 1. Fetch transcript
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.fetch(video_id, languages=["en"])
        #transcript = " ".join(item.text for item in transcript_list)
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
    except TranscriptsDisabled:
        raise ValueError("No caption available for this video")
    

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





    # 2. Split transcript
    # splitter = RecursiveCharacterTextSplitter(
    #     chunk_size=1000,
    #     chunk_overlap=200
    # )
    # chunks = splitter.create_documents([transcript])

    # 3. Pinecone ingestion guard (CRITICAL FIX)
    index = pc.Index(index_name)
    stats = index.describe_index_stats()

    if video_id not in stats.get("namespaces", {}):
        PineconeVectorStore.from_documents(
            documents=documents,
            embedding=embeddings,
            index_name=index_name,
            namespace=video_id
        )


    # 4. Vector store (retrieval only)
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


    final_prompt = prompt.invoke({
        "context": context_text,
        "question": question
    })

    answer = llm.invoke(final_prompt)

    return {
        "video_id": video_id,
        "question": question,
        "answer": answer.content
    }
