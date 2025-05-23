from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session
from config import get_db, settings
from models.chatModel.chatModel import ChatBots
from models.chatModel.sharing import ChatBotSharing
from models.authModel.authModel import AuthUser
from schemas.chatSchema.sharingSchema import (
    DirectSharingRequest, 
    EmailInviteRequest, 
    BulkEmailInviteRequest,
    AcceptInviteRequest, 
    SharingResponse, 
    InviteResponse,
    AcceptInviteResponse
)
from utils.utils import decode_access_token, get_current_user
from typing import List, Optional
from sqlalchemy import and_
import secrets
import string
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from decorators.product_status import check_product_status

router = APIRouter()

def generate_invite_token():
    """Generate a random token for invitation links"""
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))

async def send_invitation_email(recipient_email: str, invite_token: str, chatbot_name: str, owner_name: str):
    """Send invitation email to the recipient"""
    try:
        # Create message
        message = MIMEMultipart()
        message["From"] = settings.EMAIL_ADDRESS
        message["To"] = recipient_email
        message["Subject"] = f"You've been invited to collaborate on a chatbot: {chatbot_name}"
        
        # Create the invite URL
        invite_url = f"{settings.FRONTEND_URL}/accept-invite/{invite_token}"
        
        # HTML content
        html = f"""
        <html>
        <body>
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2>Chatbot Invitation</h2>
                <p>Hello,</p>
                <p>{owner_name} has invited you to collaborate on the chatbot: <strong>{chatbot_name}</strong>.</p>
                <p>Click the button below to accept this invitation:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{invite_url}" style="background-color: #4CAF50; color: white; padding: 12px 20px; text-decoration: none; border-radius: 4px; font-weight: bold;">
                        Accept Invitation
                    </a>
                </div>
                <p>Or copy and paste this link in your browser:</p>
                <p>{invite_url}</p>
                <p>This invitation link will expire in 7 days.</p>
                <p>Thank you,<br>YashMind AI Team</p>
            </div>
        </body>
        </html>
        """
        
        # Attach HTML content
        message.attach(MIMEText(html, "html"))
        
        # Connect to SMTP server and send email
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(settings.EMAIL_ADDRESS, settings.EMAIL_PASSWORD)
            server.send_message(message)
            
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

@router.post("/invite-users", response_model=InviteResponse)
@check_product_status("chatbot")
async def invite_users(
    data: BulkEmailInviteRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db)
):
    """Invite multiple users to a chatbot via email"""
    try:
        # Get current user from token
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        payload = decode_access_token(token)
        owner_id = int(payload.get("user_id"))
        owner_name = payload.get("username", "A user")
        
        # Check if chatbot exists and user is the owner
        chatbot = db.query(ChatBots).filter(
            ChatBots.id == data.bot_id,
            ChatBots.user_id == owner_id
        ).first()
        
        if not chatbot:
            raise HTTPException(status_code=404, detail="Chatbot not found or you don't have permission")
        
        # Process each email
        invites = []
        for email in data.user_emails:
            # Check if user with this email exists
            user = db.query(AuthUser).filter(AuthUser.email == email).first()
            
            # Check if sharing already exists
            existing_share = None
            if user:
                existing_share = db.query(ChatBotSharing).filter(
                    ChatBotSharing.bot_id == data.bot_id,
                    ChatBotSharing.shared_user_id == user.id
                ).first()
            else:
                existing_share = db.query(ChatBotSharing).filter(
                    ChatBotSharing.bot_id == data.bot_id,
                    ChatBotSharing.shared_email == email
                ).first()
            
            if existing_share and existing_share.status == "active":
                # Skip if already shared
                continue
            elif existing_share and existing_share.status == "pending":
                # Update existing pending invitation
                invite_token = generate_invite_token()
                existing_share.invite_token = invite_token
                existing_share.updated_at = datetime.utcnow()
                db.commit()
                db.refresh(existing_share)
                invites.append(existing_share)
                
                # Send invitation email
                background_tasks.add_task(
                    send_invitation_email,
                    email,
                    invite_token,
                    chatbot.chatbot_name,
                    owner_name
                )
            else:
                # Create new sharing record
                invite_token = generate_invite_token()
                new_sharing = ChatBotSharing(
                    bot_id=data.bot_id,
                    owner_id=owner_id,
                    shared_email=email,
                    shared_user_id=user.id if user else None,
                    invite_token=invite_token,
                    status="pending"
                )
                
                db.add(new_sharing)
                db.commit()
                db.refresh(new_sharing)
                invites.append(new_sharing)
                
                # Send invitation email
                background_tasks.add_task(
                    send_invitation_email,
                    email,
                    invite_token,
                    chatbot.chatbot_name,
                    owner_name
                )
        
        return {
            "message": f"Invitations sent to {len(invites)} users",
            "invites": invites
        }
        
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/accept-invite/{token}", response_model=AcceptInviteResponse)
async def accept_invite(
    token: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Accept an invitation using the token"""
    try:
        # Get current user from token
        auth_token = request.cookies.get("access_token")
        if not auth_token:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        payload = decode_access_token(auth_token)
        user_id = int(payload.get("user_id"))
        user_email = payload.get("sub")  # Email is stored in 'sub' claim
        
        # Find the invitation
        invitation = db.query(ChatBotSharing).filter(
            ChatBotSharing.invite_token == token,
            ChatBotSharing.status == "pending"
        ).first()
        
        if not invitation:
            raise HTTPException(status_code=404, detail="Invalid or expired invitation")
        
        # Check if the invitation matches the current user's email
        user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if invitation.shared_email and invitation.shared_email != user.email:
            raise HTTPException(
                status_code=403, 
                detail="This invitation was sent to a different email address"
            )
        
        # Update the invitation
        invitation.shared_user_id = user_id
        invitation.status = "active"
        invitation.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(invitation)
        
        return {
            "message": "Invitation accepted successfully",
            "sharing": invitation
        }
        
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/shared-chatbots", response_model=List[SharingResponse])
async def get_shared_chatbots(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get all chatbots shared with the current user"""
    try:
        # Get current user from token
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        
        # Find all active sharing records for this user
        shared_chatbots = db.query(ChatBotSharing).filter(
            ChatBotSharing.shared_user_id == user_id,
            ChatBotSharing.status == "active"
        ).all()
        
        return shared_chatbots
        
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/revoke-sharing/{sharing_id}", response_model=SharingResponse)
async def revoke_sharing(
    sharing_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Revoke a sharing by its ID"""
    try:
        # Get current user from token
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        
        # Find the sharing record
        sharing = db.query(ChatBotSharing).filter(
            ChatBotSharing.id == sharing_id
        ).first()
        
        if not sharing:
            raise HTTPException(status_code=404, detail="Sharing record not found")
        
        # Check if the current user is the owner
        if sharing.owner_id != user_id:
            raise HTTPException(status_code=403, detail="You don't have permission to revoke this sharing")
        
        # Update the status to revoked
        sharing.status = "revoked"
        sharing.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(sharing)
        
        return sharing
        
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
