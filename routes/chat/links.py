from typing import  Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
import httpx
from requests import Session
from sqlalchemy import and_, asc, desc, func, or_

from config import get_db
from decorators.product_status import check_product_status
from models.chatModel.chatModel import  ChatBots, ChatBotsDocLinks, ChatBotsFaqs
from models.subscriptions.userCredits import UserCredits
from routes.chat.celery_worker import process_document_task
from routes.chat.chat import check_available_char_limit
from routes.chat.pinecone import delete_documents_from_pinecone
from schemas.chatSchema.chatSchema import  CreateBotDocLinks, DeleteDocLinksRequest
from utils.utils import decode_access_token


router = APIRouter()


# create new chatbot doc
@router.post("/create-bot-doc-links", response_model=CreateBotDocLinks)
@check_product_status("chatbot")
async def create_chatbot_docs(
    data: CreateBotDocLinks, request: Request, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        new_chatbot_doc_links = data
        new_chatbot_doc_links.user_id = user_id

        exsiting = None
        user_credit = db.query(UserCredits).filter(UserCredits.user_id == data.user_id).first()
        current_links_count = db.query(ChatBotsDocLinks).filter(ChatBotsDocLinks.user_id == data.user_id, ChatBotsDocLinks.status != 'failed').filter(ChatBotsDocLinks.id != data.id).count()
        available_links_quota = user_credit.webpages_allowed - current_links_count
        await check_available_char_limit(user_id=user_id,db=db,new_chars=500)

        if available_links_quota <= 0:
            raise HTTPException(status_code=403,detail=f"Webpages limit Exceed. Upgrade your plan to continue")

        if data.target_link:
            exsiting = (
                db.query(ChatBotsDocLinks)
                .filter(
                    ChatBotsDocLinks.bot_id == int(data.bot_id),
                    ChatBotsDocLinks.target_link == data.target_link,
                    ChatBotsDocLinks.status != 'failed'
                )
                .first()
            )
        if data.document_link:
            exsiting = (
                db.query(ChatBotsDocLinks)
                .filter(
                    ChatBotsDocLinks.bot_id == int(data.bot_id),
                    ChatBotsDocLinks.document_link == data.document_link,
                    ChatBotsDocLinks.status != 'failed'
                )
                .first()
            )
        if exsiting and exsiting.train_from == data.train_from:
            raise HTTPException(
                status_code=400,
                detail=f"Target link already exists in {data.train_from} training.",
            )

        new_doc = ChatBotsDocLinks(
            user_id=user_id,
            bot_id=int(data.bot_id),
            chatbot_name=data.chatbot_name,
            train_from=data.train_from,
            target_link=data.target_link,
            document_link=data.document_link,
            public=data.public,
            status="pending",
            chars=0,
        )
        db.add(new_doc)
        db.commit()

        process_document_task.delay(new_doc.id)

        return new_doc

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Check doc status
@router.get("/document-status/{doc_id}")
@check_product_status("chatbot")
async def get_document_status(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(ChatBotsDocLinks).get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": doc.status}


@router.get("/get-bot-doc-links/{bot_id}")
@check_product_status("chatbot")
async def get_bot_doc_links(
    bot_id: int,
    request: Request,
    db: Session = Depends(get_db),
    search: Optional[str] = Query(
        None, description="Search by document_link or target_link"
    ),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Number of items per page"),
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        query = db.query(ChatBotsDocLinks).filter(
            # ChatBotsDocLinks.user_id == user_id,
            ChatBotsDocLinks.bot_id == bot_id,
            ChatBotsDocLinks.train_from != "full website",
        )

        # Query to get all website links (train_from = "full website")
        website_links = (
            db.query(ChatBotsDocLinks)
            .filter(
                # ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.train_from == "full website",
            )
            .all()
        )

        user_credit = (
            db.query(UserCredits).filter(UserCredits.user_id == user_id).first()
        )

        chatbot = db.query(ChatBots).filter(ChatBots.id == bot_id).first()
        if not chatbot:
            raise HTTPException(404, detail="Chatbot not found")
        
        user_bots = db.query(ChatBots).filter(ChatBots.user_id == user_id).all()


        bot_faqs = db.query(ChatBotsFaqs).filter(ChatBotsFaqs.bot_id == bot_id).all()
        user_faqs = db.query(ChatBotsFaqs).filter(ChatBotsFaqs.user_id == user_id).all()

        # Group website links by parent_link_id
        website_groups = {}
        for link in website_links:
            parent_id = link.parent_link_id  # Use id if parent_link_id is None
            if parent_id not in website_groups:
                website_groups[parent_id] = []
            website_groups[parent_id].append(link)

        # Process each website group
        websites = []
        for parent_id, links in website_groups.items():
            # Find the main/parent link (where id == parent_link_id or where parent_link_id is None)
            parent_link = next(
                (link for link in links if link.id == parent_id), links[0]
            )

            # Calculate stats for this website group
            group_total_target_links = len(links)
            group_total_document_links = sum(1 for link in links if link.document_link)

            group_pending_count = sum(
                1
                for link in links
                if link.status == "Pending" or link.status == "training"
            )
            group_failed_count = sum(1 for link in links if link.status == "failed")
            group_indexed_count = sum(1 for link in links if link.status == "indexed")

            group_total_chars = sum(link.chars or 0 for link in links)

            websites.append(
                {
                    "source": parent_link.target_link,  # The main website URL
                    "link": links,
                    "total_target_links": group_total_target_links,
                    "total_document_links": group_total_document_links,
                    "pending_count": group_pending_count,
                    "failed_count": group_failed_count,
                    "indexed_count": group_indexed_count,
                    "total_chars": group_total_chars,
                }
            )
        total_target_links = (
            db.query(ChatBotsDocLinks)
            .filter(
                # ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.train_from != "full website",
                and_(
                    ChatBotsDocLinks.target_link.isnot(None),
                    ChatBotsDocLinks.target_link != "",
                ),
            )
            .count()
        )

        user_target_links = (
            db.query(ChatBotsDocLinks)
            .filter(
                ChatBotsDocLinks.user_id == user_id,
                # ChatBotsDocLinks.bot_id == bot_id,
                and_(
                    ChatBotsDocLinks.target_link.isnot(None),
                    ChatBotsDocLinks.target_link != "",
                ),
            )
            .count()
        )

        # Count where document_link is not null and not empty
        total_document_links = (
            db.query(ChatBotsDocLinks)
            .filter(
                # ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.train_from != "full website",
                and_(
                    ChatBotsDocLinks.document_link.isnot(None),
                    ChatBotsDocLinks.document_link != "",
                ),
            )
            .count()
        )

        total_chars = (
            db.query(func.sum(ChatBotsDocLinks.chars))
            .filter(
                # ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.train_from
                != "full website",  # Exclude full website documents
            )
            .scalar()
            or 0
        )
        user_total_chars = (
            db.query(func.sum(ChatBotsDocLinks.chars))
            .filter(
                ChatBotsDocLinks.user_id == user_id,
                # ChatBotsDocLinks.bot_id== bot_id,
            )
            .scalar()
            or 0
        )

        # # First trim the text_content and count its characters
        # trimmed_text_content_bot = (
        #     chatbot.text_content.strip() if chatbot.text_content else ""
        # )
        # text_content_chars = len(trimmed_text_content_bot)

        trimmed_text_content_user = " ".join(
            chatbot.text_content.strip() if chatbot.text_content else ""
            for chatbot in user_bots
        )
        user_text_content_chars = len(trimmed_text_content_user)


        # Calculate characters from FAQs
        faqs_chars = 0
        if bot_faqs:  # Assuming bot_faqs is a list of FAQ objects
            for faq in bot_faqs:
                # Trim and count characters for both question and answer
                question = faq.question.strip() if faq.question else ""
                answer = faq.answer.strip() if faq.answer else ""
                faqs_chars += len(question) + len(answer)

        user_faq_chars = 0
        if user_faqs:  # Assuming bot_faqs is a list of FAQ objects
            for faq in user_faqs:
                # Trim and count characters for both question and answer
                question = faq.question.strip() if faq.question else ""
                answer = faq.answer.strip() if faq.answer else ""
                user_faq_chars += len(question) + len(answer)

        # Total character count
        user_total_chars += user_text_content_chars + user_faq_chars

        pending_count = (
            db.query(func.count(ChatBotsDocLinks.id))
            .filter(
                # ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                or_(
                    ChatBotsDocLinks.status == "Pending",
                    ChatBotsDocLinks.status == "training",
                ),
                ChatBotsDocLinks.train_from != "full website",
            )
            .scalar()
        )

        user_pending_count = (
            db.query(func.count(ChatBotsDocLinks.id))
            .filter(
                # ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.status == "Pending",
            )
            .scalar()
        )

        failed_count = (
            db.query(func.count(ChatBotsDocLinks.id))
            .filter(
                # ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.status == "Failed",
                ChatBotsDocLinks.train_from != "full website",
            )
            .scalar()
        )
        user_failed_count = (
            db.query(func.count(ChatBotsDocLinks.id))
            .filter(
                # ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.status == "Failed",
            )
            .scalar()
        )

        indexed_count = (
            db.query(func.count(ChatBotsDocLinks.id))
            .filter(
                # ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.status == "Indexed",
                ChatBotsDocLinks.train_from != "full website",
            )
            .scalar()
        )
        user_indexed_count = (
            db.query(func.count(ChatBotsDocLinks.id))
            .filter(
                # ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.status == "Indexed",
            )
            .scalar()
        )

        # Apply search
        if search:
            query = query.filter(
                or_(
                    ChatBotsDocLinks.document_link.ilike(f"%{search}%"),
                    ChatBotsDocLinks.target_link.ilike(f"%{search}%"),
                )
            )

        # Sorting
        sort_column = getattr(ChatBotsDocLinks, sort_by, ChatBotsDocLinks.created_at)
        sort_column = desc(sort_column) if sort_order == "desc" else asc(sort_column)
        query = query.order_by(sort_column)

        # Pagination
        total_count = query.count()
        total_pages = (total_count + limit - 1) // limit
        results = query.offset((page - 1) * limit).limit(limit).all()

        return {
            "current_page": page,
            "total_pages": total_pages,
            "total_count": total_count,
            "data": [
                {
                    "source": "links",
                    "link": results,
                    "total_target_links": total_target_links,
                    "total_document_links": total_document_links,
                    "pending_count": pending_count,
                    "failed_count": failed_count,
                    "indexed_count": indexed_count,
                    "total_chars": (
                        total_chars
                        if total_chars <= user_credit.chars_allowed
                        else user_credit.chars_allowed
                    ),
                },
                *websites,
            ],
            "Indexed": 2,
            "user_target_links": user_target_links,
            "user_pending_count": user_pending_count,
            "user_failed_count": user_failed_count,
            "user_indexed_count": user_indexed_count,
            "user_total_chars": (
                user_total_chars
                if user_total_chars <= user_credit.chars_allowed
                else user_credit.chars_allowed
            ),
            "allowed_total_chars": (
                user_credit.chars_allowed
                if user_credit and user_credit.chars_allowed
                else 0
            ),
            "allowed_total_webpages": (
                user_credit.webpages_allowed
                if user_credit and user_credit.webpages_allowed
                else 0
            ),
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete-doc-links/{bot_id}")
@check_product_status("chatbot")
async def delete_doc_links(
    bot_id: int,
    request_data: DeleteDocLinksRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        # First get all document links that will be deleted
        docs_to_delete = (
            db.query(ChatBotsDocLinks)
            .filter(
                ChatBotsDocLinks.id.in_(request_data.doc_ids),
                ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
            )
            .all()
        )

        if not docs_to_delete:
            return {"message": "No documents found to delete"}

        # Get the source links for Pinecone deletion
        doc_link_ids = [doc.id for doc in docs_to_delete]

        # Delete from Pinecone first
        deletion_stats = delete_documents_from_pinecone(bot_id, doc_link_ids, db)

        # # Clear whole pinecone
        # clear_all_pinecone_namespaces(db)

        # Then delete from database
        db.query(ChatBotsDocLinks).filter(
            ChatBotsDocLinks.id.in_(request_data.doc_ids),
            ChatBotsDocLinks.user_id == user_id,
            ChatBotsDocLinks.bot_id == bot_id,
        ).delete(synchronize_session=False)

        db.commit()

        return {
            "message": "Documents deleted successfully",
            "pinecone_deletion_stats": deletion_stats,
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

