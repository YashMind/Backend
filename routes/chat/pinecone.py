from hashlib import sha256
import os
import re
import openai
import langchain
from typing import List, Tuple, Optional
import numpy as np
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
from models.authModel.authModel import AuthUser
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
import string
import uuid
import pinecone
from rank_bm25 import BM25Okapi
import tiktoken
load_dotenv()

llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.2)
pc = pinecone.Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("yashraa-ai")  # Use your index name



# # Initialize OpenAI Embeddings
embedding_model = OpenAIEmbeddings(model="text-embedding-3-small", dimensions=1024, openai_api_key=os.getenv("OPENAI_API_KEY"))



def hybrid_retrieval(query: str, bot_id: int, top_k: int = 5) -> Tuple[List[str], List[float]]:
    try:
        # Vector Search
        query_vector = embedding_model.embed_query(query)
        
        # print(f"Query vector shape: {len(query_vector)}")
        # print(f"First few values: {query_vector[:5]}")  # Sanity check the values
        
        # Check index stats first
        # index_stats = index.describe_index_stats()
        # print(index_stats)

        # Check if your namespace exists and has vectors
        # if f"bot_{bot_id}" in index_stats['namespaces']:
        #     print(f"Namespace has {index_stats['namespaces'][f'bot_{bot_id}']['vector_count']} vectors")
        # else:
        #     print("Namespace doesn't exist or is empty")
        
        
        vector_results = index.query(
            vector=query_vector,
            top_k=max(top_k*2, 10),  # Ensure minimum 10 results
            namespace=f"bot_{bot_id}",
            include_metadata=True
        )
        
        # print("Vector results acc to query: ", vector_results)
        
        
        # test_results = index.query(
        #     vector=query_vector,
        #     top_k=5,
        #     include_metadata=True
        # )
        # print("Test results without namespace:", test_results)
    

        if not hasattr(vector_results, 'matches') or not vector_results.matches:
            return [], []
        print("if vector-results has attribute matches")
        # Text Search Preparation
        all_texts = []
        valid_matches = []
        
        for match in vector_results.matches:
            if hasattr(match, 'metadata') and match.metadata.get('content'):
                all_texts.append(match.metadata['content'])
                valid_matches.append(match)
        print("collect matches content and metadata", all_texts, valid_matches)
        if not all_texts:
            print("else returning nothing")
            return [], []

        # BM25 Scoring
        tokenized_query = query.lower().split()
        tokenized_docs = [doc.lower().split() for doc in all_texts]
        
        # Handle empty documents case
        tokenized_docs = [doc for doc in tokenized_docs if doc]
        if not tokenized_docs:
            return [], []
            
        bm25 = BM25Okapi(tokenized_docs)
        text_scores = bm25.get_scores(tokenized_query)

        # Normalize scores to avoid division issues
        vector_scores = np.array([match.score for match in valid_matches])
        text_scores = np.array(text_scores)
        
        if vector_scores.max() > 0:
            vector_scores = vector_scores / vector_scores.max()
        if text_scores.max() > 0:
            text_scores = text_scores / text_scores.max()

        # Combine scores with weights (adjust weights as needed)
        combined_scores = 0.7 * vector_scores + 0.3 * text_scores

        # Sort results
        sorted_indices = np.argsort(combined_scores)[::-1]  # Descending order
        top_results = [(all_texts[i], combined_scores[i]) for i in sorted_indices[:top_k]]
        
        if not top_results:
            return [], []
            
        return zip(*top_results)
        
    except Exception as e:
        print(f"Error in hybrid retrieval: {e}")
        return [], []

def generate_response(query: str, context: List[str], use_openai: bool, instruction_prompts, creativity, text_content) -> Tuple[str, int]:
    # Convert context to list if it's a tuple
    context = list(context) if isinstance(context, tuple) else context
    
    
    if not use_openai:
        # Simple concatenation of best matches with improved formatting
        if not context:
            return "I couldn't find relevant information in my knowledge base."
        return "Here's what I found:\n" + "\n\n".join([f"- {text}" for text in context])
    
    prompt_template = """
    You are a specialized assistant deployed on the Yashraa platform, trained to generate expert-level responses with professional clarity. Your behavior is guided by domain-specific fine-tuning, creativity calibration, and explicit instructions provided by the chatbot owner.

    Follow these steps precisely:

    1. **Analyze the Input Context:**
    - The `context` field contains raw yet high-relevance information extracted from the source website using embedding similarity (Pinecone DB).
    - If **relevant**, extract key facts and present them concisely (1–3 sentences), using accessible business language.
    - If **not relevant**, answer authoritatively using your internal knowledge.

    2. **Incorporate Fine-Tuning Parameters:**
    - **Text Content:** Incorporate tone, domain insight, or structured information provided here to shape the response.
    - **Creativity (%):** 
        - 0–30% → Strictly factual and neutral.
        - 31–70% → Professional with room for structured suggestion or interpretation.
        - 71–100% → Allow more expressive, human-like guidance while keeping accuracy intact.

    3. **Instruction Prompt Classification:**
    - Automatically determine the best-matched domain (e.g., ecommerce, hospitality, education, etc.) from `instruction_prompts` based on the nature of the question.
    - Integrate domain-specific tone, formatting, or insights if such instructions are found.

    4. **Response Guidelines:**
    - Use clear, professional, and trustworthy tone—tailored for an investor, customer, or decision-maker.
    - Focus on clarity, domain relevance, and applied intelligence.
    - Avoid generic AI phrasing or disclaimers.

    Inputs:
    - Context (scraped website content): {context}
    - User Question: {question}
    - Domain Training Content: {text_content}
    - Creativity Level (%): {creativity}
    - Instruction Prompts (Categorized): {instruction_prompts}

    Now generate a professional, fine-tuned response based on the above inputs:
    """

    # Truncate context to fit token limit more efficiently
    encoder = tiktoken.encoding_for_model("gpt-3.5-turbo")
    context_str = "\n".join(context)
    
    
    print("Context String: ",context_str )
    
    # Create a mutable copy of context for truncation
    context_list = list(context)  # Ensure we're working with a list
    
    # Calculate tokens more precisely
    while True:
        prompt = prompt_template.format(context=context_str, question=query, text_content=text_content, creativity=creativity, instruction_prompts=instruction_prompts)
        tokens = encoder.encode(prompt)
        if len(tokens) <= 3000 or not context_list:
            break
        # Remove the longest context item first
        context_list.remove(max(context_list, key=len))
        context_str = "\n".join(context_list)
    
    # if not context_str:
    #     return "I don't have enough information to answer that question."
    
    # Use invoke instead of predict
    openai_tokens = len(encoder.encode(prompt))
    print("OPENAI TOKENS: ",openai_tokens)
    try:
        response = llm.invoke(prompt)
        response_content = ""
        
        if isinstance(response, str):
            response_content = response
        elif hasattr(response, 'content'):
            response_content = response.content
        else:
            response_content = str(response)
        print("Returning")
        return response_content, openai_tokens
    
    except Exception as e:
        print(f"Error generating response: {e}")
        return "I encountered an error while processing your request.",openai_tokens

    



############################################
# training 
############################################
def clean_text(text: str) -> str:
    # Parse HTML if present
    if '<html' in text.lower() or '<body' in text.lower():
        soup = BeautifulSoup(text, 'html.parser')
        
        # Remove unwanted sections
        for tag in ['nav', 'header', 'footer', 'script', 'style']:
            for element in soup.find_all(tag):
                element.decompose()
        
        # Get cleaned text from remaining HTML
        text = soup.get_text(separator=' ', strip=True)
    
    # Remove HTML/XML tags (in case any remain)
    text = re.sub(r'<[^>]+>', '', text)
    # Remove special characters (keep letters, numbers, whitespace, hyphens)
    text = re.sub(r'[^\w\s-]', '', text)
    # Remove redundant whitespace
    text = ' '.join(text.split())
    # Remove boilerplate phrases (case insensitive)
    boilerplate = ["cookie policy", "privacy policy", "terms of use", 
                  "all rights reserved", "©", "legal notice"]
    for phrase in boilerplate:
        text = re.sub(re.escape(phrase), '', text, flags=re.IGNORECASE)
    return text.strip()

def split_documents(docs: List[Document]) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=70,
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
    namespace = f"bot_{data.bot_id}"

    for i, doc in enumerate(docs):
        try:
            text = doc.page_content
            stats['total_chars'] += len(text)
            content_hash = sha256(text.encode()).hexdigest()
            
            if content_hash in existing_hashes:
                continue
            
            # Check DB for existing hash
            if db.query(ChatBotsDocChunks).filter_by(content_hash=content_hash).first():
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
                try:
                    # Explicit namespace handling
                    response = index.upsert(
                        vectors=pinecone_vectors,
                        namespace=str(namespace)  # Force string conversion
                    )
                    print(f"Upsert response: {response}")
                    pinecone_vectors = []
                    
                    # Immediate verification
                    ns_stats = index.describe_index_stats()
                    print(f"Namespace '{namespace}' now has: {ns_stats['namespaces'].get(namespace, {}).get('vector_count', 0)} vectors")
                    
                except Exception as e:
                    print(f"Upsert error: {e}")
                    stats['failed_chunks'] += len(pinecone_vectors)
            
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
                    max_depth=2,
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

# Delete Doc
def delete_documents_from_pinecone(bot_id: int, doc_links: List[str], db: Session) -> dict:
    """
    Delete document vectors from Pinecone namespace based on source links
    Returns: {'deleted_count': int, 'errors': int}
    """
    namespace = f"bot_{bot_id}"
    stats = {'deleted_count': 0, 'errors': 0}
    
    try:
        # Get all chunks from DB that match the doc_links
        chunks = db.query(ChatBotsDocChunks).filter(
            ChatBotsDocChunks.bot_id == bot_id,
            ChatBotsDocChunks.source.in_(doc_links)
        ).all()
        
        if not chunks:
            return stats
            
        # Delete from Pinecone in batches
        batch_size = 500
        vector_ids = [str(chunk.id) for chunk in chunks]
        
        for i in range(0, len(vector_ids), batch_size):
            batch_ids = vector_ids[i:i + batch_size]
            try:
                # Delete vectors from Pinecone
                index.delete(ids=batch_ids, namespace=namespace)
                stats['deleted_count'] += len(batch_ids)
            except Exception as e:
                print(f"Error deleting batch {i}: {e}")
                stats['errors'] += len(batch_ids)
        
        # Delete from database
        db.query(ChatBotsDocChunks).filter(
            ChatBotsDocChunks.id.in_(vector_ids)
        ).delete(synchronize_session=False)
        
        db.commit()
        
    except Exception as e:
        print(f"Error in delete_documents_from_pinecone: {e}")
        db.rollback()
        stats['errors'] += len(doc_links)
        
    return stats
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