import os
import openai
import langchain
# from pinecone import Pinecone 
from langchain.document_loaders import PyPDFDirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import Pinecone
from langchain.chains.question_answering import load_qa_chain
from langchain import OpenAI
from sqlalchemy.orm import Session
from langchain.document_loaders import WebBaseLoader, PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from models.chatModel.chatModel import ChatBotsDocChunks, ChatBotsFaqs
from pathlib import Path
from difflib import SequenceMatcher
from sqlalchemy import func
from langchain.chat_models import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from typing import Optional
import string
import uuid
import pinecone
load_dotenv()

llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.2)
pc = pinecone.Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("yashraa-ai")  # Use your index name

# # Initialize OpenAI Embeddings
embedding_model = OpenAIEmbeddings(model="text-embedding-3-small", dimensions=1024, openai_api_key=os.getenv("OPENAI_API_KEY"))

# from vector database
def retrieve_answers(query:str, bot_id:int):
    query_vector = embedding_model.embed_query(query)

    # Step 2: Search Pinecone with the embedded vector
    results = index.query(
        vector=query_vector,
        top_k=5,
        namespace=f"bot_{bot_id}",
        include_metadata=True
    )
    print("result 2", results)

    # Step 3: Process the results
    best_matches = results.get("matches", [])
    if not best_matches:
        return None
        # return "No relevant information found."

    # Step 4: Extract the best result (or combine top-k)
    top_result = best_matches[0]
    answer = top_result["metadata"].get("content") or top_result["metadata"].get("text") or "No content found."

    return answer

# store data for pine coning
def process_and_store_docs(data, db: Session):
    documents = []

    # 2. Load from uploaded document
    try:
        # 1. Load from target link
        if data.target_link:
            loader = WebBaseLoader(data.target_link)
            documents = loader.load()
        elif data.document_link:
            url_path = data.document_link.lstrip("/")
            file_path = os.path.join(url_path)
            loader = PyPDFLoader(str(file_path))
            documents = loader.load()
        else:
            raise ValueError("Either target_link or document_link must be provided.")
    except Exception as e:
        print(f"Error loading PDF: {e}")
        raise

    if not documents:
        raise ValueError("No data loaded from link or file")
    
    # Create a dense index with integrated embedding
    index_name = "yashraa-ai"
    if not pc.has_index(index_name):
        pc.create_index_for_model(
            name=index_name,
            cloud="aws",
            region="us-east-1",
            embed={
                "model":"llama-text-embed-v2",
                "field_map":{"text": "chunk_text"}
            }
        )


    # 3. Split documents into chunks
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    split_docs = splitter.split_documents(documents)

    # 4. Store each chunk as row in DB
    # 4. Embed and upsert to Pinecone
    pinecone_vectors = []
    count=0
    for doc in split_docs:

        text = doc.page_content
        metadata = {
            "bot_id": str(data.bot_id),
            "user_id": str(data.user_id),
            "source": data.target_link or data.document_link,
            "content": text
        }

        try:
            embedding = embedding_model.embed_query(text)
            vector_id = str(uuid.uuid4())  # unique ID for each chunk

            # Add to Pinecone batch
            pinecone_vectors.append({
                "id": vector_id,
                "values": embedding,
                "metadata": metadata
            })

            # Optionally store in your own DB too
            db_chunk = ChatBotsDocChunks(
                bot_id=data.bot_id,
                user_id=data.user_id,
                source=metadata["source"],
                content=text,
                metaData=str(doc.metadata)
            )
            db.add(db_chunk)
            count += len(text)

        except Exception as e:
            print("Embedding error:", e)

    # Upsert all vectors to Pinecone
    if pinecone_vectors:
        try:
            dense_index = pc.Index(index_name)
            dense_index.upsert(vectors=pinecone_vectors, namespace="bot_" + str(data.bot_id))
        except Exception as e:
            print("e ", e)
            raise     
    
    db.commit()
    return  count

def get_response_from_faqs(user_msg: str, bot_id: int, db: Session):
    try:
        cleaned_msg = user_msg.lower().strip().replace('?', '')
        pattern = f"%{cleaned_msg}%"
        faq = db.query(ChatBotsFaqs).filter(
            ChatBotsFaqs.bot_id == bot_id,
            func.lower(ChatBotsFaqs.question).like(pattern)
        ).first()
        return faq if faq else None
    except Exception as e:
        return None

def get_docs_tuned_like_response(user_msg: str, bot_id: int, db: Session) ->  Optional[str]:
    # Fetch relevant document chunks
    chunks = db.query(ChatBotsDocChunks).filter_by(bot_id=bot_id).all()
    if not chunks:
        return None

    context = "\n\n".join([chunk.content for chunk in chunks if chunk.content])

    print("context ", context)

    # LangChain chat messages
    messages = [
        SystemMessage(content="You are a helpful assistant. Use only the provided context to answer."),
        HumanMessage(content=f"""
        Context:
        {context}

        Question: {user_msg}

        If the answer is not found in the context, respond with "I don't know".
        """)
        ]

    try:
        response = llm(messages)
        answer = response.content.strip()
        normalized_answer = answer.lower().strip().strip(string.punctuation)
        if normalized_answer == "i don't know":
            return None
        else:
            print("ans ", answer)
            return answer
    except Exception as e:
        print("LangChain/OpenAI error:", e)
        return None