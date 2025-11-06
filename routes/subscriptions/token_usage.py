from sqlalchemy.exc import SQLAlchemyError
from typing import Tuple, Union
from sqlalchemy.orm import Session
from models.adminModel.adminModel import SubscriptionPlans
from models.authModel.authModel import AuthUser
from models.chatModel.chatModel import ChatBots, ChatMessage, ChatSession
from models.subscriptions.token_usage import TokenUsage, TokenUsageHistory
from models.subscriptions.transactionModel import Transaction
from models.subscriptions.userCredits import UserCredits
from datetime import datetime, timedelta
from sqlalchemy import func, text
from fastapi import HTTPException


"""When user purchased new susbscription"""


def create_token_usage(
    credit_id: int, transaction_id: int, db: Session
) -> Tuple[bool, Union[str, dict]]:
    """
    Creates token usage records for a new subscription with comprehensive error handling.

    Args:
        credit_id: ID of the UserCredit record
        transaction_id: ID of the Transaction record
        db: SQLAlchemy database session

    Returns:
        Tuple: (success: bool, message: str/details: dict)
    """
    try:
        # Validate input parameters
        if not all(
            isinstance(param, int) and param > 0
            for param in [credit_id, transaction_id]
        ):
            error_msg = "Invalid input parameters: credit_id and transaction_id must be positive integers"
            print(error_msg)
            return False, error_msg

        if not db or not isinstance(db, Session):
            error_msg = "Invalid database session provided"
            print(error_msg)
            return False, error_msg

        # Begin nested transaction
        db.begin_nested()

        # Fetch credit and transaction records with error handling
        credit, transaction = None, None
        try:
            credit = db.query(UserCredits).filter(UserCredits.id == credit_id).first()
            transaction = (
                db.query(Transaction).filter(Transaction.id == transaction_id).first()
            )

            if not credit:
                error_msg = f"Credit record not found with ID: {credit_id}"
                print(error_msg)
                db.rollback()
                return False, error_msg

            if not transaction:
                error_msg = f"Transaction record not found with ID: {transaction_id}"
                print(error_msg)
                db.rollback()
                return False, error_msg

        except SQLAlchemyError as e:
            error_msg = f"Database error while fetching records: {str(e)}"
            print(f"#########    {error_msg}    #########")
            db.rollback()
            return False, error_msg

        user_id = transaction.user_id
        processed_bots = []
        failed_bots = []

        try:
            bots = db.query(ChatBots).filter(ChatBots.user_id == user_id).all()

            if not bots:
                print(f"No bots found for user ID: {user_id}")
                return (
                    True,
                    "No bots found for user - token usage initialization not required",
                )

            for bot in bots:
                try:
                    # Process each bot in a nested transaction
                    db.begin_nested()

                    existing_usage = (
                        db.query(TokenUsage)
                        .filter(
                            TokenUsage.bot_id == bot.id, TokenUsage.user_id == user_id
                        )
                        .first()
                    )

                    if existing_usage and existing_usage.user_credit_id == credit_id:
                        error_msg = f"The token usage of bot {bot.id} has already been updated under same user credit"
                        print(error_msg)
                        continue

                    if existing_usage:
                        # Archive existing usage
                        try:
                            history_entry = TokenUsageHistory(
                                bot_id=existing_usage.bot_id,
                                user_id=existing_usage.user_id,
                                user_credit_id=existing_usage.user_credit_id,
                                token_limit=existing_usage.token_limit,
                                combined_token_consumption=existing_usage.combined_token_consumption,
                                message_limit=existing_usage.message_limit,
                                combined_message_consumption=existing_usage.combined_message_consumption,
                                **{
                                    field: getattr(existing_usage, field)
                                    for field in [
                                        "open_ai_request_token",
                                        "open_ai_response_token",
                                        "user_request_token",
                                        "user_response_token",
                                        "whatsapp_request_tokens",
                                        "whatsapp_response_tokens",
                                        "slack_request_tokens",
                                        "slack_response_tokens",
                                        "wordpress_request_tokens",
                                        "wordpress_response_tokens",
                                        "zapier_request_tokens",
                                        "zapier_response_tokens",
                                        "user_request_message",
                                        "user_response_message",
                                        "whatsapp_request_messages",
                                        "whatsapp_response_messages",
                                        "slack_request_messages",
                                        "slack_response_messages",
                                        "wordpress_request_messages",
                                        "wordpress_response_messages",
                                        "zapier_request_messages",
                                        "zapier_response_messages",
                                    ]
                                },
                            )
                            db.add(history_entry)
                            db.flush()  # Test insert before proceeding
                        except SQLAlchemyError as e:
                            db.rollback()
                            error_msg = f"Failed to archive token usage for bot {bot.id}: {str(e)}"
                            print(error_msg)
                            failed_bots.append(bot.id)
                            continue

                        # Reset existing usage
                        try:
                            existing_usage.user_credit_id = credit_id
                            existing_usage.token_limit = (
                                credit.credits_purchased * credit.token_per_unit
                            )
                            existing_usage.combined_token_consumption = 0
                            existing_usage.message_limit = (
                                credit.credits_purchased * credit.message_per_unit
                            )
                            existing_usage.combined_message_consumption = 0
                            for field in [
                                "open_ai_request_token",
                                "open_ai_response_token",
                                "user_request_token",
                                "user_response_token",
                                "whatsapp_request_tokens",
                                "whatsapp_response_tokens",
                                "slack_request_tokens",
                                "slack_response_tokens",
                                "wordpress_request_tokens",
                                "wordpress_response_tokens",
                                "zapier_request_tokens",
                                "zapier_response_tokens",
                                "user_request_message",
                                "user_response_message",
                                "whatsapp_request_messages",
                                "whatsapp_response_messages",
                                "slack_request_messages",
                                "slack_response_messages",
                                "wordpress_request_messages",
                                "wordpress_response_messages",
                                "zapier_request_messages",
                                "zapier_response_messages",
                            ]:
                                setattr(existing_usage, field, 0)
                            db.flush()  # Test update before proceeding
                        except SQLAlchemyError as e:
                            db.rollback()
                            error_msg = f"Failed to reset token usage for bot {bot.id}: {str(e)}"
                            print(error_msg)
                            failed_bots.append(bot.id)
                            continue

                    else:
                        # Create new token usage
                        try:
                            new_usage = TokenUsage(
                                bot_id=bot.id,
                                user_id=user_id,
                                user_credit_id=credit_id,
                                token_limit=credit.credits_purchased
                                * credit.token_per_unit,
                                combined_token_consumption=0,
                                message_limit=credit.credits_purchased
                                * credit.message_per_unit,
                                combined_message_consumption=0,
                                **{
                                    field: 0
                                    for field in [
                                        "open_ai_request_token",
                                        "open_ai_response_token",
                                        "user_request_token",
                                        "user_response_token",
                                        "whatsapp_request_tokens",
                                        "whatsapp_response_tokens",
                                        "slack_request_tokens",
                                        "slack_response_tokens",
                                        "wordpress_request_tokens",
                                        "wordpress_response_tokens",
                                        "zapier_request_tokens",
                                        "zapier_response_tokens",
                                        "user_request_message",
                                        "user_response_message",
                                        "whatsapp_request_messages",
                                        "whatsapp_response_messages",
                                        "slack_request_messages",
                                        "slack_response_messages",
                                        "wordpress_request_messages",
                                        "wordpress_response_messages",
                                        "zapier_request_messages",
                                        "zapier_response_messages",
                                    ]
                                },
                            )
                            db.add(new_usage)
                            db.flush()
                        except SQLAlchemyError as e:
                            db.rollback()
                            error_msg = f"Failed to create token usage for bot {bot.id}: {str(e)}"
                            print(error_msg)
                            failed_bots.append(bot.id)
                            continue

                    processed_bots.append(bot.id)
                    db.commit()  # Commit the nested transaction for this bot

                except Exception as e:
                    db.rollback()
                    error_msg = f"Unexpected error processing bot {bot.id}: {str(e)}"
                    print(error_msg)
                    failed_bots.append(bot.id)
                    continue

            # Final commit if all operations succeeded
            db.commit()

            if failed_bots:
                success_msg = (
                    f"Token usage processed with partial success. "
                    f"Processed bots: {processed_bots}, Failed bots: {failed_bots}"
                )
                print(success_msg)
                return True, {
                    "success_count": len(processed_bots),
                    "failed_count": len(failed_bots),
                    "processed_bots": processed_bots,
                    "failed_bots": failed_bots,
                }

            print(f"Successfully processed token usage for bots: {processed_bots}")
            return True, {
                "success_count": len(processed_bots),
                "processed_bots": processed_bots,
            }

        except SQLAlchemyError as e:
            db.rollback()
            error_msg = f"Database error during bot processing: {str(e)}"
            print(error_msg)
            return False, error_msg

    except Exception as e:
        db.rollback()
        error_msg = f"Unexpected error in create_token_usage: {str(e)}"
        print(error_msg)
        return False, error_msg


"""Update Token useage for a topup"""


def update_token_usage_topup(
    credit_id: int, transaction_id: int, db: Session
) -> Tuple[bool, Union[str, dict]]:
    """
    Creates token usage records for a new subscription with comprehensive error handling.

    Args:
        credit_id: ID of the UserCredit record
        transaction_id: ID of the Transaction record
        db: SQLAlchemy database session

    Returns:
        Tuple: (success: bool, message: str/details: dict)
    """
    try:
        # Validate input parameters
        if not all(
            isinstance(param, int) and param > 0
            for param in [credit_id, transaction_id]
        ):
            error_msg = "Invalid input parameters: credit_id and transaction_id must be positive integers"
            print(error_msg)
            return False, error_msg

        if not db or not isinstance(db, Session):
            error_msg = "Invalid database session provided"
            print(error_msg)
            return False, error_msg

        # Begin nested transaction
        db.begin_nested()

        # Fetch credit and transaction records with error handling
        credit, transaction = None, None
        try:
            credit = db.query(UserCredits).filter(UserCredits.id == credit_id).first()
            transaction = (
                db.query(Transaction).filter(Transaction.id == transaction_id).first()
            )

            if not credit:
                error_msg = f"Credit record not found with ID: {credit_id}"
                print(error_msg)
                db.rollback()
                return False, error_msg

            if not transaction:
                error_msg = f"Transaction record not found with ID: {transaction_id}"
                print(error_msg)
                db.rollback()
                return False, error_msg

        except SQLAlchemyError as e:
            error_msg = f"Database error while fetching records: {str(e)}"
            print(error_msg)
            db.rollback()
            return False, error_msg

        user_id = transaction.user_id
        processed_bots = []
        failed_bots = []

        try:
            bots = db.query(ChatBots).filter(ChatBots.user_id == user_id).all()

            if not bots:
                print(f"No bots found for user ID: {user_id}")
                return (
                    True,
                    "No bots found for user - token usage initialization not required",
                )

            for bot in bots:
                try:
                    # Process each bot in a nested transaction
                    db.begin_nested()

                    existing_usage = (
                        db.query(TokenUsage)
                        .filter(
                            TokenUsage.bot_id == bot.id, TokenUsage.user_id == user_id
                        )
                        .first()
                    )

                    if (
                        existing_usage
                        and existing_usage.topup_transaction_id == transaction.id
                    ):
                        error_msg = f"The token usage of bot {bot.id} has already been updated under same user credit and topup transaction"
                        print(error_msg)
                        continue

                    if existing_usage:
                        # Reset existing usage
                        try:
                            existing_usage.token_limit = (
                                credit.credits_purchased * credit.token_per_unit
                            )
                            existing_usage.message_limit = (
                                credit.credits_purchased * credit.message_per_unit
                            )
                            db.flush()  # Test update before proceeding
                        except SQLAlchemyError as e:
                            db.rollback()
                            error_msg = f"Failed to reset token usage for bot {bot.id}: {str(e)}"
                            print(error_msg)
                            failed_bots.append(bot.id)
                            continue

                    else:
                        # Create new token usage
                        try:
                            new_usage = TokenUsage(
                                bot_id=bot.id,
                                user_id=user_id,
                                user_credit_id=credit_id,
                                token_limit=credit.credits_purchased
                                * credit.token_per_unit,
                                combined_token_consumption=0,
                                message_limit=credit.credits_purchased
                                * credit.message_per_unit,
                                combined_message_consumption=0,
                                **{
                                    field: 0
                                    for field in [
                                        "open_ai_request_token",
                                        "open_ai_response_token",
                                        "user_request_token",
                                        "user_response_token",
                                        "whatsapp_request_tokens",
                                        "whatsapp_response_tokens",
                                        "slack_request_tokens",
                                        "slack_response_tokens",
                                        "wordpress_request_tokens",
                                        "wordpress_response_tokens",
                                        "zapier_request_tokens",
                                        "zapier_response_tokens",
                                        "user_request_message",
                                        "user_response_message",
                                        "whatsapp_request_messages",
                                        "whatsapp_response_messages",
                                        "slack_request_messages",
                                        "slack_response_messages",
                                        "wordpress_request_messages",
                                        "wordpress_response_messages",
                                        "zapier_request_messages",
                                        "zapier_response_messages",
                                    ]
                                },
                            )
                            db.add(new_usage)
                            db.flush()
                        except SQLAlchemyError as e:
                            db.rollback()
                            error_msg = f"Failed to create token usage for bot {bot.id}: {str(e)}"
                            print(error_msg)
                            failed_bots.append(bot.id)
                            continue

                    processed_bots.append(bot.id)
                    db.commit()  # Commit the nested transaction for this bot

                except Exception as e:
                    db.rollback()
                    error_msg = f"Unexpected error processing bot {bot.id}: {str(e)}"
                    print(error_msg)
                    failed_bots.append(bot.id)
                    continue

            # Final commit if all operations succeeded
            db.commit()

            if failed_bots:
                success_msg = (
                    f"Token usage processed with partial success. "
                    f"Processed bots: {processed_bots}, Failed bots: {failed_bots}"
                )
                print(success_msg)
                return True, {
                    "success_count": len(processed_bots),
                    "failed_count": len(failed_bots),
                    "processed_bots": processed_bots,
                    "failed_bots": failed_bots,
                }

            print(f"Successfully processed token usage for bots: {processed_bots}")
            return True, {
                "success_count": len(processed_bots),
                "processed_bots": processed_bots,
            }

        except SQLAlchemyError as e:
            db.rollback()
            error_msg = f"Database error during bot processing: {str(e)}"
            print(error_msg)
            return False, error_msg

    except Exception as e:
        db.rollback()
        error_msg = f"Unexpected error in create_token_usage: {str(e)}"
        print(error_msg)
        return False, error_msg


"""Verify if token consumption limit available"""


def verify_token_limit_available(bot_id: int, db: Session):
    """Check if a bot has available token limits."""
    try:
        bot_token_usage = db.query(TokenUsage).filter_by(bot_id=bot_id).first()
        if not bot_token_usage:
            return False, "Token usage plan is not available for this bot"

        # if bot_token_usage.token_limit > bot_token_usage.combined_token_consumption:
        #     return True, "Token limit available for this bot"

        if bot_token_usage.message_limit > bot_token_usage.combined_message_consumption:
            return True, "Message limit available for this bot"
        else:
            return False, "No Message Limit available for this bot"

    except Exception as e:
        error_msg = f"Unexpected error in verify_token_limit_available: {str(e)}"
        print(error_msg)
        return False, error_msg


"""Update token usage on consumption."""


def update_token_usage_on_consumption(
    bot_id: int, consumed_token, consumed_token_type: str, db: Session
):
    try:
        print(f"Updating token usage for bot_id: {bot_id}, token_type: {consumed_token_type}")
        print(f"Consumed Token: {consumed_token.__dict__ if hasattr(consumed_token, '__dict__') else consumed_token}")

        # Retrieve the bot's token usage data from the database
        bot_token_usage = db.query(TokenUsage).filter_by(bot_id=bot_id).first()
        if not bot_token_usage:
            print(f"No TokenUsage found for bot_id: {bot_id}")
            return False, "Bot token usage not found"
        print(f"TokenUsage found: {bot_token_usage.__dict__}")

        # Retrieve subordinate bots' token usage data
        subordinate_bots = db.query(TokenUsage).filter_by(user_id=bot_token_usage.user_id).all()
        print(f"Found {len(subordinate_bots)} subordinate bots for user_id: {bot_token_usage.user_id}")

        # Retrieve user's credit info
        credit = db.query(UserCredits).filter_by(id=bot_token_usage.user_credit_id).first()
        if not credit:
            print(f"No UserCredits found for credit_id: {bot_token_usage.user_credit_id}")
            return False, "User credit info not found"
        print(f"UserCredits found: {credit.__dict__}")

        if consumed_token_type == "direct_bot":
            print("Updating for direct_bot")
            bot_token_usage.user_request_token += consumed_token.request_token
            bot_token_usage.user_response_token += consumed_token.response_token
            bot_token_usage.user_request_message += consumed_token.request_message
            bot_token_usage.user_response_message += consumed_token.response_message
        elif consumed_token_type == "whatsapp_bot":
            print("Updating for whatsapp_bot")
            bot_token_usage.whatsapp_request_tokens += consumed_token.request_token
            bot_token_usage.whatsapp_response_tokens += consumed_token.response_token
            bot_token_usage.whatsapp_request_messages += consumed_token.request_message
            bot_token_usage.whatsapp_response_messages += consumed_token.response_message
        elif consumed_token_type == "slack_bot":
            print("Updating for slack_bot")
            bot_token_usage.slack_request_tokens += consumed_token.request_token
            bot_token_usage.slack_response_tokens += consumed_token.response_token
            bot_token_usage.slack_request_messages += consumed_token.request_token
            bot_token_usage.slack_response_messages += consumed_token.response_token
        elif consumed_token_type == "zapier_bot":
            print("Updating for zapier_bot")
            bot_token_usage.zapier_request_tokens += consumed_token.request_token
            bot_token_usage.zapier_response_tokens += consumed_token.response_token
            bot_token_usage.zapier_request_messages += consumed_token.request_token
            bot_token_usage.zapier_response_messages += consumed_token.response_token
        else:
            print(f"Unknown consumed_token_type: {consumed_token_type}")
            return False, "Invalid token type"

        # Common update for all bot types
        bot_token_usage.open_ai_request_token += consumed_token.open_ai_request_token
        bot_token_usage.open_ai_response_token += consumed_token.open_ai_response_token

        print("Updated bot_token_usage tokens")

        # update all subordinate bots combined token usage data
        consumption_stats = (
            consumed_token.request_token + consumed_token.response_token
        )
        consumption_stats_message = (
            consumed_token.request_message + consumed_token.response_message
        )
        print(f"Consumption stats to add: {consumption_stats}")
        print(f"Consumption stats to add: {consumption_stats_message}")

        for subordinate_bot in subordinate_bots:
            print(f"Before update - Bot ID {subordinate_bot.bot_id}: combined_token_consumption={subordinate_bot.combined_token_consumption}")
            subordinate_bot.combined_token_consumption += consumption_stats
            print(f"After update - Bot ID {subordinate_bot.bot_id}: combined_token_consumption={subordinate_bot.combined_token_consumption}")
            subordinate_bot.combined_message_consumption += consumption_stats_message
            print(f"After update - Bot ID {subordinate_bot.bot_id}: combined_message_consumption={subordinate_bot.combined_message_consumption}")
            db.add(subordinate_bot)
            db.flush()

        total_token_consumption = bot_token_usage.combined_token_consumption
        total_message_consumption = bot_token_usage.combined_message_consumption
        print(f"Total token consumption: {total_token_consumption}")

        db.query(AuthUser).filter(AuthUser.id == bot_token_usage.user_id).update(
            {AuthUser.tokenUsed: total_token_consumption, AuthUser.messageUsed: total_message_consumption}
        )
        print(f"Updated AuthUser.tokenUsed and AuthUsed.messageUsed for user_id={bot_token_usage.user_id}")
        credits_consumed = (total_token_consumption // credit.token_per_unit) + (
            1 if total_token_consumption % credit.token_per_unit > 0 else 0
        )

        print(f"Total token consumption: {total_message_consumption}")

        # check user plan here if plan is enterprise, then use entity base_rate_per_message from user table not message_per_unit from user credit
        
        user = db.query(AuthUser).filter(AuthUser.id == bot_token_usage.user_id).first()
        user_plan = db.query(SubscriptionPlans).filter(SubscriptionPlans.id == user.plan).filter(SubscriptionPlans.is_enterprise == True).first()
        if user_plan and user.base_rate_per_message:
            credits_consumed_messages = (total_message_consumption // user.base_rate_per_message) + (
            1 if total_message_consumption % credit.message_per_unit > 0 else 0
            )
        else:
            credits_consumed_messages = (total_message_consumption // credit.message_per_unit) + (
                1 if total_message_consumption % credit.message_per_unit > 0 else 0
            )
        balance_credits = credit.credits_purchased - credits_consumed
        balance_credits_messages = credit.credits_purchased - credits_consumed_messages

        print(f"Credits consumed Token: {credits_consumed}")
        print(f"Credits consumed Message: {credits_consumed_messages}")
        print(f"Balance credits: {balance_credits}")

        credit.credits_consumed = credits_consumed
        credit.credits_consumed_messages = credits_consumed_messages
        credit.credit_balance = balance_credits
        credit.credit_balance_messages = balance_credits_messages

        db.add(credit)

        db.commit()
        print("Database commit successful")
        return True, "All Consumption data updated successfully"

    except Exception as e:
        error_msg = f"Unexpected error in update_token_usage_on_consumption: {str(e)}"
        print(error_msg)
        return False, error_msg


"""Generate token usage entry for a new bot."""


def generate_token_usage(bot_id, user_id, db: Session):
    # Create a new token usage entry for the new bot
    # get user credits using user id
    # if user id exists

    # get suborditnate bots using user_id
    # if subordinate bots exist, get their combined token usage data
    # else, set combined token usage data to 0
    # else
    # return with error not plan active

    user_credits = db.query(UserCredits).filter_by(user_id=user_id).first()
    if user_credits:
        combined_token_consumption = 0
        combined_message_consumption = 0
        token_limit = user_credits.credits_purchased * user_credits.token_per_unit
        message_limit = user_credits.credits_purchased * user_credits.message_per_unit
        subordinate_bots = db.query(TokenUsage).filter_by(user_id=user_id).all()
        if subordinate_bots:
            combined_token_consumption = subordinate_bots[0].combined_token_consumption
            token_limit = subordinate_bots[0].token_limit

        if subordinate_bots:
            combined_message_consumption = subordinate_bots[0].combined_message_consumption
            message_limit = subordinate_bots[0].message_limit

        token_usage = TokenUsage(
            bot_id=bot_id,
            user_id=user_id,
            user_credit_id=user_credits.id,
            token_limit=token_limit,
            combined_token_consumption=combined_token_consumption,
            message_limit=message_limit,
            combined_message_consumption=combined_message_consumption,
        )
        db.add(token_usage)
        db.commit()

        return True, "Token usage entry created successfully"
    else:
        return False, "User not found, please activate plan"
    
    
    
# def check_rate_limit(bot_id: int, user_id: int, db, chatbot):
#     """
#     Enforces per-bot rate limit (X messages per Y minutes).
#     Raises HTTPException if the limit is exceeded.
#     """

#     if not chatbot.rate_limit_enabled:
#         return True

#     limit_to = chatbot.limit_to or 0
#     every_minutes = chatbot.every_minutes or 0

#     if limit_to <= 0 or every_minutes <= 0:
#         return True  # invalid config, skip limiting

#     # Time window start
#     time_threshold = datetime.utcnow() - timedelta(minutes=every_minutes)

#     # Count messages sent by users (not bots) for this bot in the time window
#     message_count = (
#         db.query(func.count())
#         .select_from(ChatMessage)
#         .filter(
#             ChatMessage.bot_id == bot_id,
#             ChatMessage.sender == "user",
#             ChatMessage.created_at >= time_threshold,
#         )
#         .scalar()
#     )

#     if message_count >= limit_to:
#         raise HTTPException(
#             status_code=429,
#             detail=f"Rate limit exceeded: Only {limit_to} messages allowed every {every_minutes} minutes.",
#         )

#     return True



def check_rate_limit(
    bot_id: int,
    user_id: int,
    db,
    chatbot,
    *,
    per_user: bool = True,
    session_token: str | None = None,
):
    if not chatbot or not chatbot.rate_limit_enabled:
        return True

    limit_to = (chatbot.limit_to or 0)
    every_minutes = (chatbot.every_minutes or 0)
    if limit_to <= 0 or every_minutes <= 0:
        return True

    # figure DB dialect
    try:
        dialect = db.bind.dialect.name
    except Exception:
        dialect = None

    # Build DB-side time expression
    if dialect == "postgresql":
        time_expr = func.now() - text(f"interval '{every_minutes} minutes'")
    elif dialect in ("mysql", "mariadb"):
        # MySQL: DATE_SUB(NOW(), INTERVAL X MINUTE)
        time_expr = func.date_sub(func.now(), text(f"interval {every_minutes} minute"))
    elif dialect == "sqlite":
        # SQLite: datetime('now','-N minutes')
        time_expr = func.datetime("now", f"-{every_minutes} minutes")
    else:
        # Unknown: fall back to Python UTC (best-effort)
        time_expr = datetime.utcnow() - timedelta(minutes=every_minutes)

    # If session_token given -> count by chat session
    if session_token:
        chat = db.query(ChatSession).filter_by(token=session_token).first()
        if not chat:
            return True

        q = db.query(func.count()).select_from(ChatMessage).filter(
            ChatMessage.chat_id == chat.id,
            ChatMessage.sender == "user",
        )
        # use DB time_expr when possible
        if isinstance(time_expr, datetime):
            q = q.filter(ChatMessage.created_at >= time_expr)
        else:
            q = q.filter(ChatMessage.created_at >= time_expr)
        message_count = q.scalar() or 0

        if message_count >= limit_to:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: Only {limit_to} messages allowed every {every_minutes} minutes.",
            )
        return True

    # Fallback counting (per_user/per_bot)
    q = db.query(func.count()).select_from(ChatMessage).filter(
        ChatMessage.bot_id == bot_id,
        ChatMessage.sender == "user",
    )

    if isinstance(time_expr, datetime):
        q = q.filter(ChatMessage.created_at >= time_expr)
    else:
        q = q.filter(ChatMessage.created_at >= time_expr)

    if per_user and user_id is not None:
        q = q.filter(ChatMessage.user_id == user_id)

    message_count = q.scalar() or 0
    if message_count >= limit_to:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: Only {limit_to} messages allowed every {every_minutes} minutes.",
        )
    return True
