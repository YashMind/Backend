from hashlib import sha256
import os
import re
import openai
import langchain
# from pinecone import Pinecone 
from langchain.document_loaders import PyPDFDirectoryLoader
from langchain.document_loaders import RecursiveUrlLoader
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
from langchain.schema import HumanMessage, SystemMessage, Document
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from langchain.document_loaders import (
    WebBaseLoader,
    PyPDFLoader,
    Docx2txtLoader,
    TextLoader,
    CSVLoader,
    UnstructuredExcelLoader,
    UnstructuredPowerPointLoader,
    UnstructuredFileLoader
)
from typing import List, Optional
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
    score = top_result.get("score", 0)

    if score < 0.90:
        return None
    answer = top_result["metadata"].get("content") or top_result["metadata"].get("text") or "No content found."

    return answer


############################################
# training 
############################################
def clean_text(text: str) -> str:
    # Remove HTML/XML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove special characters
    text = re.sub(r'[^\w\s-]', '', text)
    # Remove redundant whitespace
    text = ' '.join(text.split())
    # Remove boilerplate phrases
    boilerplate = ["cookie policy", "privacy policy", "terms of use"]
    for phrase in boilerplate:
        text = text.replace(phrase, '')
    return text.strip()

def split_documents(docs: List[Document]) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=250,
        separators=["\n\n##", "\n\n", "\n", ". "],
        length_function=len
    )
    return splitter.split_documents(docs)

def get_loader_for_file(file_path: str):
    if file_path.endswith('.pdf'):
        return PyPDFLoader(file_path)
    elif file_path.endswith('.docx'):
        return Docx2txtLoader(file_path)
    elif file_path.endswith('.txt'):
        return TextLoader(file_path)
    elif file_path.endswith('.csv'):
        return CSVLoader(file_path)
    elif file_path.endswith('.xlsx') or file_path.endswith('.xls'):
        return UnstructuredExcelLoader(file_path)
    elif file_path.endswith('.pptx'):
        return UnstructuredPowerPointLoader(file_path)
    else:
        return UnstructuredFileLoader(file_path)

def preprocess_documents(docs: List[Document]) -> List[Document]:
    processed = []
    for doc in docs:
        # Clean text
        text = clean_text(doc.page_content)
        
        # Normalize metadata
        metadata = normalize_metadata(doc.metadata)
        
        processed.append(Document(
            page_content=text,
            metadata=metadata
        ))
    return processed

def normalize_metadata(metadata: dict) -> dict:
    # Standardize metadata keys
    standard_meta = {}
    for k, v in metadata.items():
        standard_meta[k.lower()] = str(v)
    return standard_meta

def store_documents(docs: List[Document], data, db: Session) -> dict:
    """Store documents and return processing statistics"""
    
    existing_hashes = set()
    batch_size = 200
    pinecone_vectors = []
    stats = {
        'total_chars': 0,
        'chunks_processed': 0,
        'failed_chunks': 0
    }

    for i, doc in enumerate(docs):
        try:
            text = doc.page_content
            stats['total_chars'] += len(text)
            content_hash = sha256(text.encode()).hexdigest()
            
            if content_hash in existing_hashes:
                continue
            
            # Check DB for existing hash
            if db.query(ChatBotsDocChunks.id).filter_by(content_hash=content_hash).first():
                continue
            metadata = {
                "bot_id": str(data.bot_id),
                "user_id": str(data.user_id),
                "source": data.target_link or data.document_link,
                "content": text,
                "chunk_index": i,
                **doc.metadata
            }
            
            embedding = embedding_model.embed_query(text)
            
            pinecone_vectors.append({
                "id": str(uuid.uuid4()),
                "values": embedding,
                "metadata": metadata
            })
            existing_hashes.add(content_hash)
            
            if len(pinecone_vectors) >= batch_size or i == len(docs)-1:
                index.upsert(vectors=pinecone_vectors)
                pinecone_vectors = []
            
            db_chunk = ChatBotsDocChunks(
                bot_id=data.bot_id,
                user_id=data.user_id,
                source=metadata["source"],
                content=text,
                metaData=str(metadata),
                chunk_index=i,
                char_count=len(text)  # Store char count per chunk
            )
            db.add(db_chunk)
            stats['chunks_processed'] += 1
            
        except Exception as e:
            print(f"Error storing chunk {i}: {e}")
            stats['failed_chunks'] += 1
            continue
    
    db.commit()
    return stats

# store data for pine coning
def process_and_store_docs(data, db: Session) -> dict:
    """Process documents and return metadata including character counts"""
    documents = []
    stats = {
        'total_chars': 0,
        'total_chunks': 0,
        'sources': set(),
        'file_types': set()
    }

    try:
        print("=== Start: process_and_store_docs ===")
        print("Received data:", data)

        # Handle web content
        if data.target_link:
            print("Target link detected:", data.target_link)
            if data.train_from == "Full website":
                print("Training from full website...")
                loader = RecursiveUrlLoader(
                    url=data.target_link,
                    max_depth=1,
                    extractor=lambda x: BeautifulSoup(x, "html.parser").text
                )
                stats['source_type'] = 'website'
            else:
                print("Training from single page...")
                loader = WebBaseLoader(data.target_link)
                stats['source_type'] = 'single_page'
            documents = loader.load()
            print(f"Loaded {len(documents)} documents from web.")
            stats['sources'].add(data.target_link)

        # Handle file uploads
        elif data.document_link:
            print("Document link detected:", data.document_link)
            file_path = data.document_link.lstrip("/")
            print("Sanitized file path:", file_path)
            loader = get_loader_for_file(file_path)
            documents = loader.load()
            print(f"Loaded {len(documents)} documents from file.")
            file_type = os.path.splitext(file_path)[1][1:]  # Get extension without dot
            stats['file_types'].add(file_type)
            stats['source_type'] = 'file'
            stats['sources'].add(file_path)

        if not documents:
            raise ValueError("No data loaded from link or file")

        # Pre-process documents (clean, normalize)
        print("Preprocessing documents...")
        cleaned_docs = preprocess_documents(documents)
        print(f"Preprocessed into {len(cleaned_docs)} documents.")

        # Chunking with overlap
        print("Splitting documents into chunks...")
        split_docs = split_documents(cleaned_docs)
        print(f"Generated {len(split_docs)} chunks.")
        stats['total_chunks'] = len(split_docs)

        # Store in vector DB and SQL while counting characters
        print("Storing documents...")
        store_results = store_documents(split_docs, data, db)
        stats['total_chars'] = store_results['total_chars']
        print("Total characters stored:", stats['total_chars'])

        # Convert sets to lists for JSON serialization
        stats['sources'] = list(stats['sources'])
        stats['file_types'] = list(stats['file_types'])

        print("=== End: process_and_store_docs ===")
        return stats['total_chars']

    except Exception as e:
        print(f"Error processing documents: {e}")
        raise


############################################
# training 
############################################


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