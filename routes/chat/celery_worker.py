from celery import Celery
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.chatModel.chatModel import ChatBotsDocLinks
from routes.chat.pinecone import process_and_store_docs

celery = Celery(__name__, broker='redis://localhost:6379/0')
engine = create_engine("mysql+pymysql://user:pass@db_host/db_name")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@celery.task
def process_document_task(doc_id: int):
    db = SessionLocal()
    try:
        doc_entry = db.query(ChatBotsDocLinks).get(doc_id)
        doc_entry.status = "training"
        db.commit()
        
        # Your existing processing logic
        chars_count = process_and_store_docs(doc_entry, db)
        
        doc_entry.status = "trained"
        doc_entry.chars = chars_count
        db.commit()
    except Exception as e:
        doc_entry.status = "failed"
        db.commit()
        raise e
    finally:
        db.close()