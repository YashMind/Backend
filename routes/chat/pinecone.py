import os
import openai
import langchain
from pinecone import Pinecone 
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
load_dotenv()

llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.2)
# pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
# index = pc.index("yashraa-ai")  # Use your index name

# # Initialize OpenAI Embeddings
# embedding_model = OpenAIEmbeddings(openai_api_key=os.getenv("OPENAI_API_KEY"))

# def read_doc(directory):
#     file_loader=PyPDFDirectoryLoader(directory)
#     documents=file_loader.load()
#     return documents

# doc=read_doc('documents/')
# len(doc)

# def chunk_data(docs,chunk_size=800,chunk_overlap=50):
#     text_splitter=RecursiveCharacterTextSplitter(chunk_size=chunk_size,chunk_overlap=chunk_overlap)
#     doc=text_splitter.split_documents(docs)
#     return doc

# documents=chunk_data(docs=doc)
# # len(documents)

# embeddings=OpenAIEmbeddings(api_key=os.getenv('OPENAI_API_KEY'))
# # embeddings

# vectors=embeddings.embed_query("How are you?")
# # len(vectors)

# # pinecone.init(
# #     api_key="923d5299-ab4c-4407-bfe6-7f439d9a9cb9",
# #     environment="gcp-starter"
# # )
# index_name="yashraa-ai"

# # index=Pinecone.from_documents(doc,embeddings,index_name=index_name)
# pc = Pinecone(
#     api_key=os.getenv("PINECONE_API_KEY"),
# )
# index = pc.index(index_name)

# def retrieve_query(query,k=2):
#     matching_results=index.similarity_search(query,k=k)
#     return matching_results

# llm=OpenAI(model_name="text-davinci-003",temperature=0.5)
# chain=load_qa_chain(llm,chain_type="stuff")

# # from vector database
# def retrieve_answers(query):
#     doc_search=retrieve_query(query)
#     if not doc_search:
#         return ""
#     response=chain.run(input_documents=doc_search,question=query)
#     return response

# fine tuning
def process_and_store_docs(data, db: Session):
    documents = []

    # 1. Load from target link
    if data.target_link:
        loader = WebBaseLoader(data.target_link)
        documents = loader.load()

    # 2. Load from uploaded document
    elif data.document_link:
        url_path = data.document_link.lstrip("/")
        file_path = os.path.join(url_path)
        try:
            loader = PyPDFLoader(str(file_path))
            documents = loader.load()
        except Exception as e:
            print(f"Error loading PDF: {e}")
            raise

    if not documents:
        raise ValueError("No data loaded from link or file")

    # 3. Split documents into chunks
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    split_docs = splitter.split_documents(documents)

    # 4. Store each chunk as row in DB
    # 4. Embed and upsert to Pinecone
    pinecone_vectors = []
    count=0
    for doc in split_docs:
        count+=len(doc.page_content)
        db_chunk = ChatBotsDocChunks(
            bot_id=data.bot_id,
            user_id=data.user_id,
            source=data.target_link or data.document_link,
            content=doc.page_content,
            metaData=str(doc.metadata)
        )
        db.add(db_chunk)
        # text = doc.page_content
        # metadata = {
        #     "bot_id": str(data.bot_id),
        #     "user_id": str(data.user_id),
        #     "source": data.target_link or data.document_link
        # }

        # try:
        #     embedding = embedding_model.embed_query(text)
        #     vector_id = str(uuid.uuid4())  # unique ID for each chunk

        #     # Add to Pinecone batch
        #     pinecone_vectors.append({
        #         "id": vector_id,
        #         "values": embedding,
        #         "metadata": metadata
        #     })

        #     # Optionally store in your own DB too
        #     db_chunk = ChatBotsDocChunks(
        #         bot_id=data.bot_id,
        #         user_id=data.user_id,
        #         source=metadata["source"],
        #         content=text,
        #         metaData=str(doc.metadata)
        #     )
        #     db.add(db_chunk)
        #     count += len(text)

        # except Exception as e:
        #     print("Embedding error:", e)

    # Upsert all vectors to Pinecone
    # if pinecone_vectors:
    #     index.upsert(vectors=pinecone_vectors, namespace="bot_" + str(data.bot_id))     
    
    db.commit()
    return  count

def get_response_from_faqs(user_msg: str, bot_id: int, db: Session):
    cleaned_msg = user_msg.lower().strip().replace('?', '')
    pattern = f"%{cleaned_msg}%"
    faq = db.query(ChatBotsFaqs).filter(
        ChatBotsFaqs.bot_id == bot_id,
        func.lower(ChatBotsFaqs.question).like(pattern)
    ).first()
    return faq if faq else None

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