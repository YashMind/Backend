from celery import Celery
from models.chatModel.chatModel import ChatBotsDocLinks
from routes.chat.pinecone import process_and_store_docs
from config import SessionLocal

celery = Celery(__name__, broker="redis://localhost:6379/0")

i = celery.control.inspect()
active_tasks = i.active()
print(active_tasks)


@celery.task
def process_document_task(doc_id: int):
    db = SessionLocal()
    try:
        print(f"[DEBUG] Fetching document with ID: {doc_id}")
        doc_entry = db.query(ChatBotsDocLinks).get(doc_id)

        if not doc_entry:
            print(f"[ERROR] No document found with ID: {doc_id}")
            return

        print(
            f"[DEBUG] Retrieved doc_entry: ID={doc_entry.id}, train_from={doc_entry.train_from}"
        )

        doc_entry.status = "training"

        if doc_entry.train_from == "Full website":
            doc_entry.parent_link_id = doc_entry.id
            print(f"[DEBUG] Set parent_link to self: {doc_entry.parent_link_id}")

        print(f"[DEBUG] Tables in metadata: {Base.metadata.tables.keys()}")
        db.commit()
        print(f"[DEBUG] Committed training status and parent_link update")

        # Your existing processing logic
        chars_count = process_and_store_docs(doc_entry, db)
        print(f"[DEBUG] Document processed. Total characters: {chars_count}")

        doc_entry.status = "trained"
        doc_entry.chars = chars_count
        db.commit()
        print(f"[DEBUG] Updated status to 'trained' and saved char count")

    except Exception as e:
        print(f"[ERROR] Exception during document processing: {e}")
        db.rollback()  # ⬅️ Add this
        if doc_entry:
            doc_entry.status = "failed"
            db.commit()
        raise e

    finally:
        db.close()
        print(f"[DEBUG] DB session closed")
