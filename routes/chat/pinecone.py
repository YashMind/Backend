import os
import openai
import langchain
import pinecone 
from langchain.document_loaders import PyPDFDirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import Pinecone
from langchain.chains.question_answering import load_qa_chain
from langchain import OpenAI
from dotenv import load_dotenv
load_dotenv()

def read_doc(directory):
    file_loader=PyPDFDirectoryLoader(directory)
    documents=file_loader.load()
    return documents

doc=read_doc('documents/')
len(doc)

def chunk_data(docs,chunk_size=800,chunk_overlap=50):
    text_splitter=RecursiveCharacterTextSplitter(chunk_size=chunk_size,chunk_overlap=chunk_overlap)
    doc=text_splitter.split_documents(docs)
    return doc

documents=chunk_data(docs=doc)
# len(documents)

embeddings=OpenAIEmbeddings(api_key=os.getenv('OPENAI_API_KEY'))
# embeddings

vectors=embeddings.embed_query("How are you?")
# len(vectors)

# pinecone.init(
#     api_key="923d5299-ab4c-4407-bfe6-7f439d9a9cb9",
#     environment="gcp-starter"
# )
index_name="langchainvector"

# index=Pinecone.from_documents(doc,embeddings,index_name=index_name)
pc = Pinecone(
    api_key=os.getenv("PINECONE_API_KEY"),
)
index = pc.Index(index_name)

def retrieve_query(query,k=2):
    matching_results=index.similarity_search(query,k=k)
    return matching_results

llm=OpenAI(model_name="text-davinci-003",temperature=0.5)
chain=load_qa_chain(llm,chain_type="stuff")

# from vector database
def retrieve_answers(query):
    doc_search=retrieve_query(query)
    if not doc_search:
        return ""
    response=chain.run(input_documents=doc_search,question=query)
    return response