import os
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import PromptTemplate
from pinecone import Pinecone, ServerlessSpec
from langchain_pinecone import PineconeVectorStore
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

First, try to answer using the transcript of the youtube video/podcast.
If the transcript does NOT contain enough information:
- Clearly say: "The following answer is not based on the transcript. I do not have sufficient information from the transcript. So the following answer is based on my general knowledge."
- Then answer the question using your general knowledge.
- Before this try very hard to find the answer in the transcript.

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
        transcript = " ".join(item.text for item in transcript_list)
    except TranscriptsDisabled:
        raise ValueError("No caption available for this video")

    # 2. Split transcript
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )
    chunks = splitter.create_documents([transcript])

    # 3. Pinecone ingestion guard (CRITICAL FIX)
    index = pc.Index(index_name)
    stats = index.describe_index_stats()

    if video_id not in stats.get("namespaces", {}):
        PineconeVectorStore.from_documents(
            documents=chunks,
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
    context_text = "\n\n".join(doc.page_content for doc in docs)

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
