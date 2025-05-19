# from celery import Celery
from models.chatModel.chatModel import ChatBotsDocLinks
from routes.chat.pinecone import process_and_store_docs
from config import SessionLocal

# celery = Celery(__name__, broker='redis://localhost:6379/0')

# i = celery.control.inspect()
# active_tasks = i.active()
# print(active_tasks)


# @celery.task
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