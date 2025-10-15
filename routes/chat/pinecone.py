from hashlib import sha256
import html
import os
from pathlib import Path
import re
import tempfile
import time
from typing import List, Tuple, Optional
from urllib.parse import urlparse
import numpy as np

# from pinecone import Pinecone
from langchain_core.language_models.llms import BaseLLM
from langchain.document_loaders import RecursiveUrlLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import ChatGoogleGenerativeAI
import olefile
import regex
import requests
from sqlalchemy.orm import Session
from langchain.document_loaders import WebBaseLoader, PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from models.adminModel.toolsModal import ToolsUsed
from models.chatModel.chatModel import (
    ChatBotsDocChunks,
    ChatBotsDocLinks,
    ChatBotsFaqs,
    ChatMessage,
)
from sqlalchemy import func
from langchain.chat_models import ChatOpenAI
from langchain.schema import Document
from sqlalchemy.orm import Session
from bs4 import BeautifulSoup
from langchain.document_loaders import (
    WebBaseLoader,
    PyPDFLoader,
    Docx2txtLoader,
    TextLoader,
    CSVLoader,
    UnstructuredWordDocumentLoader,
    UnstructuredExcelLoader,
    UnstructuredPowerPointLoader,
    UnstructuredFileLoader,
)
from docx2txt import process
import uuid
import pinecone
from pinecone import ServerlessSpec
from rank_bm25 import BM25Okapi
import tiktoken
from config import SessionLocal, get_db
from models.subscriptions.userCredits import UserCredits
from utils.DeepSeek import DeepSeekLLM
from utils.convertDocToDocx import convert_doc_to_docx
from utils.embeddings import get_embeddings
import logging

pc = pinecone.Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

index_name = "yashraa-ai"
desired_dimension = 768
metric = "cosine"
spec = ServerlessSpec(cloud="aws", region="us-east-1")

# Check if index exists
existing_indexes = pc.list_indexes()
existing_indexes = [i.get("name") for i in existing_indexes]
print("EXISTING INEXES: ", existing_indexes)

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


if index_name in existing_indexes:
    description = pc.describe_index(index_name)
    current_dimension = description.dimension

    if current_dimension != desired_dimension:
        print(
            f"⚠️ Index '{index_name}' has dimension {current_dimension}, expected {desired_dimension}. Deleting and recreating..."
        )
        # pc.delete_index(index_name)
        pc.create_index(
            name=index_name, dimension=desired_dimension, metric=metric, spec=spec
        )
        print(f"✅ Index '{index_name}' recreated with dimension {desired_dimension}")
    else:
        print(
            f"✅ Index '{index_name}' already has correct dimension {desired_dimension}"
        )
else:
    print(f"ℹ️ Index '{index_name}' does not exist. Creating it...")
    pc.create_index(
        name=index_name, dimension=desired_dimension, metric=metric, spec=spec
    )
    print(f"✅ Index '{index_name}' created with dimension {desired_dimension}")

# Connect to the index
index = pc.Index(index_name)


def get_llm(tool: str, model_name: str, temperature: float = 0.2) -> BaseLLM:
    """Get the appropriate language model for each tool"""
    if tool == "ChatGPT":
        return ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
    elif tool == "DeepSeek":
        return DeepSeekLLM(model_name=model_name, temperature=temperature)
    elif tool == "Gemini":
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
        )
    else:
        raise ValueError(f"Unsupported tool: {tool}")


def hybrid_retrieval(
    tool,
    db: Session,
    query: str,
    bot_id: int,
    top_k: int = 5,
) -> Tuple[List[str], List[float]]:
    try:
        # Vector Search
        embedding_model = get_embeddings(tool=tool.tool)
        query_vector = embedding_model.embed_query(query)

        print(f"Query vector shape: {len(query_vector)}")
        print(f"First few values: {query_vector[:5]}")  # Sanity check the values

        # Check index stats first
        index_stats = index.describe_index_stats()
        print("NAMESPACE INDEX STATS", index_stats)

        # Check if your namespace exists and has vectors
        if f"bot_{bot_id}" in index_stats["namespaces"]:
            print(
                f"Namespace has {index_stats['namespaces'][f'bot_{bot_id}']['vector_count']} vectors"
            )
        else:
            print("Namespace doesn't exist or is empty")

        vector_results = index.query(
            vector=query_vector,
            top_k=max(top_k * 2, 10),  # Ensure minimum 10 results
            namespace=f"bot_{bot_id}",
            include_metadata=True,
        )

        # print("Vector results acc to query: ", vector_results.matches)

        # test_results = index.query(
        #     vector=query_vector,
        #     top_k=5,
        #     include_metadata=True
        # )
        # print("Test results without namespace:", test_results)

        if not hasattr(vector_results, "matches") or not vector_results.matches:
            return [], []
        print("if vector-results has attribute matches")
        # Text Search Preparation
        all_texts = []
        valid_matches = []
        # print("MATCHED VECTOR RESULTS: ", vector_results.matches)
        for match in vector_results.matches:
            if hasattr(match, "metadata"):
                metadata = match.metadata or {}

                print("Match ID: ", match.id)
                db_chunk = (
                    db.query(ChatBotsDocChunks).filter_by(chunk_index=match.id).first()
                )

                if not db_chunk:
                    print("Chunk not found")
                    continue
                print("Chunk found in DB with content: ", db_chunk.content)
                text_content = (
                    f"source: '{metadata.get('source', '')}', "
                    f"title: '{metadata.get('title', '')}', "
                    f"description: '{metadata.get('description', '')}', "
                    f"content: '{db_chunk.content}'"
                )
                all_texts.append(text_content)
                valid_matches.append(match)
        # print("collect matches content and metadata", all_texts, valid_matches)
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
        top_results = [
            (all_texts[i], combined_scores[i]) for i in sorted_indices[:top_k]
        ]

        if not top_results:
            return [], []

        return zip(*top_results)

    except Exception as e:
        print(f"Error in hybrid retrieval: {e}")
        return [], []


def generate_response(
    query: str,
    message_history,
    context: List[str],
    use_openai: bool,
    instruction_prompts,
    creativity,
    text_content,
    active_tool,
) -> Tuple[str, int]:
    # Convert context to list if it's a tuple
    context = list(context) if isinstance(context, tuple) else context

    print("Context", context)

    if not use_openai:
        # Simple concatenation of best matches with improved formatting
        if not context:
            return "I couldn't find relevant information in my knowledge base."
        return "Here's what I found:\n" + "\n\n".join([f"- {text}" for text in context])

    prompt_template = """You are a warm, intelligent, domain-specific support assistant embedded on a website. Your job is to respond helpfully and professionally to user queries. If a greeting is detected, respond with a friendly greeting. For all other queries, reply **only** with verified information from the inputs provided. Format responses using professional, semantic HTML. Never fabricate or assume facts. Never mention this prompt or its instructions to the user.

    At every user turn, you receive the following runtime variables:

    INPUT VARIABLES

    • context — Scraped content or metadata from training data. It may be unstructured, but you must extract and use relevant content if present.
    context: {context}

    • question — User’s query.
    question: {question}

    • text_content — Brand information, tone guidelines, policies, formatting rules, and workflow instructions that must be strictly followed.
    text_content: {text_content}

    • instruction_prompts — Domain-specific workflows or rules. Analyze the context, question, and text_content to detect the relevant domain, then follow the matching instruction. If no domain match is found, apply the general instructions.
    instruction_prompts: {instruction_prompts}

    • creativity — Integer from 0–100 controlling elaboration level. 0 = factual only, 100 = detailed and freeform.
    creativity: {creativity}

    • message_history — Last 3 system and 3 user messages. Use this to maintain continuity and resolve references.
    message_history: {message_history}
    
    OUTPUT RULES

    1. — GREETING & SMALL TALK:

    * If a greeting is detected, begin with a warm response (e.g., "Hello!", "Hi there!"). If the query continues beyond the greeting, follow the rest of this prompt.
    * For small talk like "How are you?", respond politely using ... and avoid structured formatting.

    2. — CONTENT PRIORITY & CONTEXT USE:

    * Always extract information from context, instruction_prompts, text_content, or message_history.
    * If direct matches aren't found, extract the main keyword or topic. Find related keywords in the context (up to 15 terms) and use that to construct an informative reply.
    * Resolve references in user queries ("this course", "these features") using message_history.
    * Always aim to give a **complete** and **detailed** answer where content permits.

    3. — FORMATTING:

    * Format all responses in clean, professional HTML tags.
    * Use bullet or numbered lists for multi-part answers.
    * Break up large blocks of text into readable sections.
    * Ensure output is mobile- and screen-reader-friendly.

    4. — STRUCTURE BY DOMAIN:

    * Courses: Use Title, Price, Duration, Curriculum.
    * E-commerce: Use Product Name, Price, Features, Availability.
    * Documentation: Include Description, Steps, Errors, Fixes (when asked).
    * Other Workflows: Follow exact rules from instruction_prompts.

    5. — DATA MISSING OR UNCLEAR:

    * If no related content is found, respond with: Apologies, I do not have that information. Please contact our support team for further assistance.
    * If a support/help URL is provided in text_content or instruction_prompts, append:

    6. — TONE AND ENGAGEMENT:

    * Maintain a warm, positive, and helpful tone.
    * Use phrases like "Glad you asked", "Let me help with that", or "Here’s what I found".
    * Conclude with an invitation to follow up if relevant (e.g., "Feel free to ask more!").

    7. — FACTUALITY:

    * Never invent, guess, or exaggerate.
    * Only respond with information found in the inputs.
    * Do not include placeholders or incomplete references.
    * If a source URL is full and used, append that as anchor tag link to find more information here.
    """

    # Truncate context to fit token limit more efficiently
    encoder = tiktoken.encoding_for_model("gpt-3.5-turbo")
    context_str = "\n".join(str(item) for item in context) if context else ""

    print(f"Original Context String: {context_str}")

    # Create a mutable copy of context for truncation
    context_list = list(context) if context else []  # Ensure we're working with a list

    # Calculate tokens more precisely
    # while True:
    prompt = prompt_template.format(
        context=context_str,
        question=query,
        text_content=text_content,
        creativity=creativity,
        instruction_prompts=instruction_prompts,
        message_history=message_history,
    )
    # print("formatted prompt: ",prompt)
    # tokens = encoder.encode(prompt)
    # if len(tokens) <= 5000 or not context_list:
    #     break
    # # Remove the longest context item first
    # context_list.remove(max(context_list, key=len))
    # context_str = "\n".join(str(item) for item in context_list)

    # Final check for empty context
    # if not context_str.strip():
    #     return "I don't have enough information to answer that question."

    # Debug print formatted prompt
    print(f"Final Prompt: {prompt}")

    # Use invoke instead of predict
    openai_request_tokens = len(encoder.encode(prompt))
    print("OPENAI TOKENS: ", openai_request_tokens)

    llm = get_llm(
        tool=active_tool.tool,
        model_name=active_tool.model if active_tool else "gpt-3.5-turbo",
        temperature=1.3,
    )

    try:

        print(
            f"""
              ################################################################################
              {prompt}
              ################################################################################
              """
        )
        response = llm.invoke(prompt)
        response_content = ""

        if isinstance(response, str):
            response_content = response
        elif hasattr(response, "content"):
            response_content = response.content
        else:
            response_content = str(response)
        print("Returning")

        print("Cleaning: ", response_content)
        cleaned_response = re.sub(
            r"```(html|json)?", "", response_content, flags=re.IGNORECASE
        )
        cleaned_response = re.sub(r"```", "", cleaned_response)
        cleaned_response = cleaned_response.strip()

        # Remove HTML tags if the text appears to be in HTML format
        if re.search(r"<[a-z][\s\S]*>", cleaned_response, re.IGNORECASE):
            cleaned_response = re.sub(r"<[^>]+>", "", cleaned_response)
            cleaned_response = cleaned_response.strip()

        cleaned_response = re.sub(r"\s+", " ", cleaned_response).strip()

        print("Cleaned Response: ", cleaned_response)

        openai_response_tokens = len(encoder.encode(cleaned_response))
        request_tokens = len(encoder.encode(query))

        return (
            response_content,
            openai_request_tokens,
            openai_response_tokens,
            request_tokens,
        )

    except Exception as e:
        print(f"Error generating response: {e}")
        return (
            "I encountered an error while processing your request.",              
                    openai_request_tokens,
            0,
        )


############################################
# training
############################################
def extract_main_content(html):
    soup = BeautifulSoup(html, "html.parser")

    # Remove unwanted tags
    for tag in ["script", "style", "header", "footer", "nav", "aside"]:
        for el in soup.find_all(tag):
            el.decompose()

    # Optionally target specific content divs like WordPress's "entry-content"
    main = soup.find("main") or soup.find("div", class_="entry-content")
    if main:
        return main.get_text(separator="\n", strip=True)

    # fallback to body if no main content found
    return soup.body.get_text(separator="\n", strip=True) if soup.body else ""


def clean_text(text: str) -> str:
    # Step 1: HTML parsing if present
    if "<html" in text.lower() or "<body" in text.lower():
        soup = BeautifulSoup(text, "html.parser")
        for tag in ["nav", "header", "footer", "script", "style"]:
            for element in soup.find_all(tag):
                element.decompose()
        text = soup.get_text(separator=" ", strip=True)
        text = html.unescape(text)

    # Step 2: Strip any remaining HTML tags
    text = regex.sub(r"<[^>]+>", "", text)

    # Step 3: Remove non-text symbols
    text = regex.sub(r"[^\p{L}\p{N}_\s\p{Sc}\.,:;/\-]", "", text, flags=regex.UNICODE)

    # Step 4: Remove excess whitespace
    text = " ".join(text.split())

    # Step 5: Remove boilerplate
    boilerplate = [
        "cookie policy",
        "privacy policy",
        "terms of use",
        "all rights reserved",
        "©",
        "legal notice",
    ]
    for phrase in boilerplate:
        text = regex.sub(re.escape(phrase), "", text, flags=regex.IGNORECASE)

    return text.strip()


def split_documents(docs: List[Document]) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=2500,
        chunk_overlap=500,
        separators=["\n\n##", "\n\n", "\n", ". "],
        length_function=len,
    )
    return splitter.split_documents(docs)


def get_loader_for_file(file_path: str):
    if file_path.endswith(".pdf"):
        return PyPDFLoader(file_path)
    elif file_path.endswith(".docx"):
        return Docx2txtLoader(file_path)
    elif file_path.endswith(".txt"):
        return TextLoader(file_path)
    elif file_path.endswith(".csv"):
        return CSVLoader(file_path)
    elif file_path.endswith(".xlsx") or file_path.endswith(".xls"):
        return UnstructuredExcelLoader(file_path)
    elif file_path.endswith(".pptx"):
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

        processed.append(Document(page_content=text, metadata=metadata))
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
    stats = {"total_chars": 0, "chunks_processed": 0, "failed_chunks": 0}
    namespace = f"bot_{data.bot_id}"
    if not data.user_id:
        raise ValueError("User ID is required to store documents")
    user_credit = (
        db.query(UserCredits).filter(UserCredits.user_id == data.user_id).first()
    )
    total_docs = (
        db.query(ChatBotsDocChunks.content)
        .filter(ChatBotsDocChunks.user_id == data.user_id)
        .all()
    )
    total_doc_chars = sum(len(row.content) for row in total_docs if row.content)

    print(f"[DEBUG] Namespace to use: {namespace}")

    for i, doc in enumerate(docs):
        try:
            text = doc.page_content
            if len(text) + total_doc_chars > user_credit.chars_allowed:
                print("Exceeded Total char limit")
                raise Exception("CHAR_LIMIT_EXCEEDED: Exceeded total character limit")
            stats["total_chars"] += len(text)
            content_hash = sha256(text.encode()).hexdigest()

            if content_hash in existing_hashes:
                print(f"[DEBUG] Skipping duplicate hash in batch: {content_hash}")
                continue

            # Check DB for existing hash
            if (
                db.query(ChatBotsDocChunks)
                .filter_by(content_hash=content_hash, bot_id=data.bot_id)
                .first()
            ):
                print(f"[DEBUG] Skipping existing DB hash: {content_hash}")
                continue

            source = data.target_link
            if data.train_from == "Full website":
                source = doc.metadata["source"]
            elif data.document_link:
                source = data.document_link

            metadata = {
                **doc.metadata,
                "bot_id": str(data.bot_id),
                "user_id": str(data.user_id),
                "source": source,
                # "content": text,
                "chunk_index": i,
            }
            active_tool = db.query(ToolsUsed).filter_by(status=True).first()
            embedding_model = get_embeddings(tool=active_tool.tool)
            embedding = embedding_model.embed_query(text)
            # print("TEXT EMBEDDING: ", embedding)
            print("TEXT EMBEDDING: ", text)

            vector_id = str(uuid.uuid4())

            pinecone_vectors.append(
                {"id": vector_id, "values": embedding, "metadata": metadata}
            )
            existing_hashes.add(content_hash)

            if len(pinecone_vectors) >= batch_size:
                try:
                    print(
                        f"[DEBUG] Upserting {len(pinecone_vectors)} vectors to namespace '{namespace}'"
                    )
                    response = index.upsert(
                        vectors=pinecone_vectors, namespace=str(namespace)
                    )
                    print(f"[DEBUG] Upsert response: {response}")
                    pinecone_vectors = []

                    try:
                        time.sleep(2)
                        ns_stats = index.describe_index_stats()
                        if namespace in ns_stats["namespaces"]:
                            print(
                                f"[DEBUG] Namespace '{namespace}' now has: {ns_stats['namespaces'][namespace]['vector_count']} vectors"
                            )
                        else:
                            print(
                                f"Namespace not immediately available - try again later"
                            )
                    except Exception as e:
                        print(f"Error getting stats: {e}")

                except Exception as e:
                    print(f"[ERROR] Upsert error: {e}")
                    stats["failed_chunks"] += len(pinecone_vectors)
                    pinecone_vectors = []

            if i == len(docs) - 1 and pinecone_vectors:
                print(
                    f"[WARN] Final document skipped with {len(pinecone_vectors)} pending vectors"
                )

            print("Creating DB CHUNK")
            doc_link_id = data.id
            print(
                f"[DEBUG] Starting chunk save. doc_link_id initially set to: {doc_link_id}"
            )

            if data.train_from == "Full website":
                print(
                    "[DEBUG] Training from full website. Looking for existing child doc link..."
                )

                doc_link = (
                    db.query(ChatBotsDocLinks)
                    .filter(
                        ChatBotsDocLinks.bot_id == data.bot_id,
                        ChatBotsDocLinks.parent_link_id == data.id,
                        ChatBotsDocLinks.target_link == metadata["source"],
                    )
                    .first()
                )

                if doc_link:
                    print(f"[DEBUG] Existing doc link found: ID={doc_link.id}")
                else:
                    print("[DEBUG] No existing doc link found. Creating new one...")
                    doc_link = ChatBotsDocLinks(
                        bot_id=data.bot_id,
                        user_id=data.user_id,
                        parent_link_id=data.id,
                        target_link=metadata["source"],
                        chatbot_name=data.chatbot_name,
                        train_from=data.train_from,
                        document_link=data.document_link,
                        public=data.public,
                        status="trained",
                        chars=len(text),
                    )
                    db.add(doc_link)
                    db.flush()  # Get generated ID
                    print(f"[DEBUG] New doc link created with ID={doc_link.id}")

                doc_link_id = doc_link.id
                print(f"[DEBUG] Final doc_link_id set to: {doc_link_id}")

            # Saving chunk
            print(
                f"[DEBUG] Preparing to save chunk: vector_id={vector_id}, chars={len(text)}"
            )
            print(
                f"[DEBUG] Chunk metadata (trimmed): {str(metadata)[:200]}..."
            )  # Truncated print
            print(f"[DEBUG] Chunk content hash: {content_hash}")
            source = data.target_link
            if data.train_from == "Full website":
                source = metadata["source"]
            elif data.document_link:
                source = data.document_link

            db_chunk = ChatBotsDocChunks(
                bot_id=data.bot_id,
                user_id=data.user_id,
                source=source,
                content=text,
                metaData=str(metadata),
                chunk_index=vector_id,
                char_count=len(text),
                link_id=doc_link_id,
                content_hash=content_hash,
            )

            print("[DEBUG] SAVING DB CHUNK")
            db.add(db_chunk)
            stats["chunks_processed"] += 1
            print(
                f"[DEBUG] Chunks processed count updated to: {stats['chunks_processed']}"
            )

        except Exception as e:
            print(f"[ERROR] Error storing chunk {i}: {e}")
            if "CHAR_LIMIT_EXCEEDED" in str(e):
                raise Exception(f"{e}")
            stats["failed_chunks"] += 1
            continue
    if pinecone_vectors:
        try:
            print(
                f"[DEBUG] Upserting FINAL batch of {len(pinecone_vectors)} vectors to '{namespace}'"
            )
            response = index.upsert(vectors=pinecone_vectors, namespace=str(namespace))
            print(f"[DEBUG] Final upsert response: {response}")

            # Optional: Namespace stats check
            try:
                time.sleep(2)
                ns_stats = index.describe_index_stats()
                if namespace in ns_stats["namespaces"]:
                    print(
                        f"[DEBUG] Namespace '{namespace}' now has: {ns_stats['namespaces'][namespace]['vector_count']} vectors"
                    )
            except Exception as e:
                print(f"Error getting stats: {e}")

        except Exception as e:
            print(f"[ERROR] Final upsert failed: {e}")
            stats["failed_chunks"] += len(pinecone_vectors)
        finally:
            pinecone_vectors = []  # Prevent duplicate processing

    db.commit()
    print(f"[INFO] Final stats: {stats}")
    return stats


from urllib.parse import urlparse, urlunparse


class InternalOnlyRecursiveUrlLoader(RecursiveUrlLoader):
    def __init__(self, base_domain, *args, **kwargs):
        self.base_domain = base_domain
        self.seen_clean_urls = set()
        super().__init__(*args, **kwargs)

    def _get_links(self, soup, base_url):
        all_links = super()._get_links(soup, base_url)
        filtered_links = []

        logger.warning(f"\n[DEBUG] Scanning {len(all_links)} links from {base_url}")

        for link in all_links:
            parsed = urlparse(link)
            cleaned_link = urlunparse(parsed._replace(query="", fragment=""))

            logger.warning(f"\n→ Original: {link}")
            logger.warning(f"→ Cleaned : {cleaned_link}")

            if parsed.netloc and parsed.netloc != self.base_domain:
                logger.warning("   ⛔ Skipped: external domain")
                continue

            if parsed.query:
                logger.warning("   ⛔ Skipped: query parameter")
                continue

            if any(
                cleaned_link.lower().endswith(ext)
                for ext in [
                    ".css",
                    ".js",
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".gif",
                    ".svg",
                    ".woff",
                    ".ttf",
                    ".eot",
                    ".ico",
                    ".pdf",
                    ".zip",
                    ".rar",
                ]
            ):
                logger.warning("   ⛔ Skipped: static asset")
                continue

            if any(
                skip in cleaned_link
                for skip in [
                    "wp-content",
                    "wp-includes",
                    "feed",
                    "tag",
                    "author",
                    "cart",
                    "checkout",
                    "my-account",
                ]
            ):
                logger.warning("   ⛔ Skipped: system path")
                continue

            if cleaned_link in self.seen_clean_urls:
                logger.warning("   ⛔ Skipped: already seen")
                continue

            self.seen_clean_urls.add(cleaned_link)
            filtered_links.append(cleaned_link)
            logger.warning("   ✅ Added")

        logger.warning(
            f"\n[DEBUG] {len(filtered_links)} unique internal links will be followed next.\n"
        )
        return filtered_links


# store data for pine coning
def process_and_store_docs(data, db: Session) -> dict:
    """Process documents and return metadata including character counts"""
    documents = []
    stats = {"total_chars": 0, "total_chunks": 0, "sources": set(), "file_types": set()}

    try:
        print("=== Start: process_and_store_docs ===")
        print("Received data:", data)

        # Handle web content
        if data.target_link:
            print("Target link detected:", data.target_link)

            if data.target_link.lower().endswith((".pdf", ".docx", ".doc")):
                print("Training from document URL:", data.target_link)
                downloaded_file_path = None
                try:
                    # Download the file
                    response = requests.get(data.target_link)
                    response.raise_for_status()

                    # Generate unique filename and save to uploads directory
                    ext = os.path.splitext(data.target_link)[1].lower()
                    filename = f"{uuid.uuid4()}{ext}"
                    downloaded_file_path = UPLOADS_DIR / filename

                    with open(downloaded_file_path, "wb") as f:
                        f.write(response.content)

                    # Use the appropriate loader
                    if ext == ".pdf":
                        data.train_from = "Pdf"
                        loader = PyPDFLoader(str(downloaded_file_path))
                        stats["source_type"] = "pdf_url"
                        documents = loader.load()

                    elif ext == ".docx":
                        data.train_from = "Word doc"
                        try:
                            loader = Docx2txtLoader(str(downloaded_file_path))
                            documents = loader.load()
                        except Exception as e:
                            print(
                                f"DOCX parsing failed, trying alternative method: {e}"
                            )
                            doc = Document(downloaded_file_path)
                            text = "\n".join([para.text for para in doc.paragraphs])
                            documents = [Document(page_content=text)]

                    elif ext == ".doc":
                        data.train_from = "Word doc"
                        try:
                            # Try to read as OLE file (legacy DOC)
                            if olefile.isOleFile(str(downloaded_file_path)):
                                text = process(str(downloaded_file_path))
                                documents = [Document(page_content=text)]
                            else:
                                raise ValueError("Not a valid OLE file")
                        except Exception as e:
                            print(f"DOC parsing failed: {e}")

                            # Check if it's actually a misnamed .docx file
                            try:
                                print("Trying .docx fallback for .doc file...")
                                converted_path = convert_doc_to_docx(
                                    downloaded_file_path, "uploads/"
                                )
                                downloaded_file_path = Path(converted_path)
                                loader = Docx2txtLoader(converted_path)
                                documents = loader.load()
                            except Exception as docx_fallback_error:
                                print(
                                    f".docx fallback also failed: {docx_fallback_error}"
                                )
                                # Final fallback to binary read
                                with open(downloaded_file_path, "rb") as f:
                                    text = f.read().decode("latin-1", errors="ignore")
                                documents = [Document(page_content=text)]

                    print(f"Loaded {len(documents)} documents from {data.train_from}")

                except Exception as e:
                    print(f"Error processing document URL: {str(e)}")
                    raise
                finally:
                    # Clean up the downloaded file
                    if downloaded_file_path and downloaded_file_path.exists():
                        try:
                            os.unlink(downloaded_file_path)
                            print(f"Cleaned up temporary file: {downloaded_file_path}")
                        except Exception as cleanup_error:
                            print(
                                f"Warning: Could not delete file {downloaded_file_path}: {cleanup_error}"
                            )

            elif data.train_from == "Full website":
                print("Training from full website...")
                parsed = urlparse(data.target_link)
                base_domain = parsed.netloc  # e.g. "yashmind.in"
                loader = InternalOnlyRecursiveUrlLoader(
                    base_domain=base_domain,
                    url=data.target_link,
                    max_depth=2,
                    extractor=extract_main_content,
                )
                stats["source_type"] = "website"
                documents = loader.load()
                print(f"Loaded {len(documents)} documents from web.(Full website)")
                stats["sources"].add(data.target_link)

            else:
                print("Training from single page...")
                data.train_from = "Webpage"
                loader = WebBaseLoader(data.target_link)
                stats["source_type"] = "single_page"
                documents = loader.load()
                print(f"Loaded {len(documents)} documents from web.(Webpage)")
                stats["sources"].add(data.target_link)

        # Handle file uploads
        elif data.document_link:
            print("Document link detected:", data.document_link)
            file_path = data.document_link.lstrip("/")
            print("Sanitized file path:", file_path)
            loader = get_loader_for_file(file_path)
            documents = loader.load()
            print(f"Loaded {len(documents)} documents from file.")
            file_type = os.path.splitext(file_path)[1][1:]  # Get extension without dot
            stats["file_types"].add(file_type)
            stats["source_type"] = "file"
            stats["sources"].add(file_path)

        if not documents:
            raise ValueError("No data loaded from link or file")
        
        user_credit = db.query(UserCredits).filter(UserCredits.user_id == data.user_id).first()
        current_links_count = db.query(ChatBotsDocLinks).filter(ChatBotsDocLinks.user_id == data.user_id).filter(ChatBotsDocLinks.id != data.id).count()
        available_links_quota = user_credit.webpages_allowed - current_links_count

        if available_links_quota > 0:
            documents = documents[:available_links_quota]
        else:
            raise ValueError("Webpages limit exceeded")

        # Pre-process documents (clean, normalize)
        print("Preprocessing documents...")
        total_chars = sum(len(doc.page_content) for doc in documents)
        print(f"Document text size: {total_chars} characters")
        cleaned_docs = preprocess_documents(documents)
        print(f"Preprocessed into {len(cleaned_docs)} documents.")
        total_chars = sum(len(doc.page_content) for doc in cleaned_docs)
        print(f"Cleaned document text size: {total_chars} characters")

        # Chunking with overlap
        print("Splitting documents into chunks...")
        split_docs = split_documents(cleaned_docs)
        print(f"Generated {len(split_docs)} chunks.")
        stats["total_chunks"] = len(split_docs)

        # Store in vector DB and SQL while counting characters
        print("Storing documents...")
        store_results = store_documents(split_docs, data, db)
        stats["total_chars"] = store_results["total_chars"]
        print("Total characters stored:", stats["total_chars"])

        # Convert sets to lists for JSON serialization
        stats["sources"] = list(stats["sources"])
        stats["file_types"] = list(stats["file_types"])

        print("=== End: process_and_store_docs ===")
        return stats["total_chars"]

    except Exception as e:
        print(f"Error processing documents: {e}")
        raise


# Delete Doc
def delete_documents_from_pinecone(
    bot_id: int, doc_link_ids: List[str], db: Session
) -> dict:
    """
    Delete document vectors from Pinecone namespace based on source links
    Returns: {'deleted_count': int, 'errors': int}
    """
    namespace = f"bot_{bot_id}"
    stats = {"deleted_count": 0, "errors": 0}
    print(f"[DEBUG] Namespace for deletion: {namespace}")
    print(f"[DEBUG] Document links to delete: {doc_link_ids}")

    try:
        # Get all chunks from DB that match the doc_links
        chunks = (
            db.query(ChatBotsDocChunks)
            .filter(
                ChatBotsDocChunks.bot_id == bot_id,
                ChatBotsDocChunks.link_id.in_(doc_link_ids),
            )
            .all()
        )
        print(f"[DEBUG] Found {len(chunks)} matching chunks in DB.")

        if not chunks:
            print("[INFO] No chunks found to delete.")
            return stats

        # Prepare vector IDs for deletion
        batch_size = 500
        vector_ids = [str(chunk.chunk_index) for chunk in chunks]
        chunk_ids = [chunk.id for chunk in chunks]
        print(f"[DEBUG] Total vector IDs to delete: {len(vector_ids)}")

        for i in range(0, len(vector_ids), batch_size):
            batch_ids = vector_ids[i : i + batch_size]
            try:
                print(f"[DEBUG] Deleting batch {i//batch_size + 1}: {batch_ids}")
                index.delete(ids=batch_ids, namespace=namespace)
                stats["deleted_count"] += len(batch_ids)
                print(f"[DEBUG] Deleted batch {i//batch_size + 1} successfully.")
            except Exception as e:
                print(f"[ERROR] Error deleting batch {i//batch_size + 1}: {e}")
                stats["errors"] += len(batch_ids)

        # Delete from database
        print(f"[DEBUG] Deleting {len(chunk_ids)} chunks from DB.")
        db.query(ChatBotsDocChunks).filter(ChatBotsDocChunks.id.in_(chunk_ids)).delete(
            synchronize_session=False
        )

        db.commit()
        print(f"[INFO] Deletion complete. Stats: {stats}")

    except Exception as e:
        print(f"Error in delete_documents_from_pinecone: {e}")
        db.rollback()
        stats["errors"] += len(doc_link_ids)

    return stats


def clear_all_pinecone_namespaces(db: Session) -> dict:
    """
    Deletes all vectors from all Pinecone namespaces corresponding to all bots.
    Returns: {'namespaces_cleared': int, 'errors': List[str]}
    """
    errors = []
    namespaces_cleared = 0

    # Get unique bot_ids from the DB
    try:
        ns_stats = index.describe_index_stats()
        all_namespaces = ns_stats.get("namespaces", {}).keys()
        print(
            f"[DEBUG] Found {len(all_namespaces)} bot_ids for namespace deletion: {all_namespaces}"
        )
    except Exception as e:
        print(f"[ERROR] Failed to fetch bot_ids: {e}")
        return {"namespaces_cleared": 0, "errors": [str(e)]}

    for bot_id in all_namespaces:
        namespace = f"{bot_id}"
        try:
            index.delete(delete_all=True, namespace=namespace)
            print(f"[INFO] Cleared namespace: {namespace}")
            namespaces_cleared += 1
        except Exception as e:
            error_msg = f"Failed to delete namespace {namespace}: {e}"
            print(f"[ERROR] {error_msg}")
            errors.append(error_msg)

    return {"namespaces_cleared": namespaces_cleared, "errors": errors}


############################################
# training
############################################


def get_response_from_faqs(user_msg: str, bot_id: int, db: Session):
    try:
        cleaned_msg = user_msg.lower().strip().replace("?", "")
        pattern = f"%{cleaned_msg}%"
        faq = (
            db.query(ChatBotsFaqs)
            .filter(
                ChatBotsFaqs.bot_id == bot_id,
                func.lower(ChatBotsFaqs.question).like(pattern),
            )
            .first()
        )
        return faq if faq else None
    except Exception as e:
        return None


# def get_docs_tuned_like_response(
#     user_msg: str, bot_id: int, db: Session
# ) -> Optional[str]:
#     # Fetch relevant document chunks
#     chunks = db.query(ChatBotsDocChunks).filter_by(bot_id=bot_id).all()
#     if not chunks:
#         return None

#     context = "\n\n".join([chunk.content for chunk in chunks if chunk.content])

#     print("context ", context)

#     # LangChain chat messages
#     messages = [
#         SystemMessage(
#             content="You are a helpful assistant. Use only the provided context to answer."
#         ),
#         HumanMessage(
#             content=f"""
#         Context:
#         {context}

#         Question: {user_msg}

#         If the answer is not found in the context, respond with "I don't know".
#         """
#         ),
#     ]

#     try:
#         response = llm(messages)
#         answer = response.content.strip()
#         normalized_answer = answer.lower().strip().strip(string.punctuation)
#         if normalized_answer == "i don't know":
#             return None
#         else:
#             print("ans ", answer)
#             return answer
#     except Exception as e:
#         print("LangChain/OpenAI error:", e)
#         return None
