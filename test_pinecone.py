from dotenv import load_dotenv
load_dotenv()

import os
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import PromptTemplate
from pinecone import Pinecone, ServerlessSpec
from langchain_pinecone import PineconeVectorStore
from urllib.parse import urlparse, parse_qs


def extract_video_id(youtube_url: str) -> str:
    parsed_url = urlparse(youtube_url)

    # Case 1: https://www.youtube.com/watch?v=VIDEO_ID
    if parsed_url.hostname in ("www.youtube.com", "youtube.com"):
        return parse_qs(parsed_url.query).get("v", [None])[0]

    # Case 2: https://youtu.be/VIDEO_ID
    if parsed_url.hostname == "youtu.be":
        return parsed_url.path.lstrip("/")

    return None





# 1. Fetch YouTube transcript
youtube_url = "https://www.youtube.com/watch?v=ay37uluXwhI&list=PL8qRqB6F6d9ZkOhrZTbvS6tCk8MeEbyCe&index=20"

video_id = extract_video_id(youtube_url)

if not video_id:
    print("Invalid YouTube URL")
    raise SystemExit

try:
    api = YouTubeTranscriptApi()
    transcript_list = api.fetch(video_id, languages=["en"])
    transcript = " ".join(item.text for item in transcript_list)

except TranscriptsDisabled:
    print("No caption available for this video")
    raise SystemExit



# 2. Split transcript
splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200
)
chunks = splitter.create_documents([transcript])




# 3. Embeddings
embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small"
)



# 4. Initialize Pinecone
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

index_name = "youtube-chatbot"

# Create index if it does not exist
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

index = pc.Index(index_name)



# 5. Create Pinecone vector store
vector_store = PineconeVectorStore.from_documents(
    documents=chunks,
    embedding=embeddings,
    index_name=index_name,
    namespace=video_id
)


# 6. Retriever
retriever = vector_store.as_retriever(
    search_type="similarity",
    search_kwargs={"k": 4}
)



# 7. LLM
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0
)



# 8. Prompt
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



# 9. Ask questions
question = "In this podcast Write about spirituality?"

docs = retriever.invoke(question)
context_text = "\n\n".join(doc.page_content for doc in docs)

final_prompt = prompt.invoke({
    "context": context_text,
    "question": question
})

answer = llm.invoke(final_prompt)
print(answer.content)
