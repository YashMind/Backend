from sqlalchemy.exc import SQLAlchemyError
from typing import Tuple, Union
from sqlalchemy.orm import Session
from models.chatModel.chatModel import ChatBots
from models.subscriptions.token_usage import TokenUsage, TokenUsageHistory
from models.subscriptions.transactionModel import Transaction
from models.subscriptions.userCredits import UserCredits


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

        if bot_token_usage.token_limit > bot_token_usage.combined_token_consumption:
            return True, "Token limit available for this bot"

    except Exception as e:
        error_msg = f"Unexpected error in verify_token_limit_available: {str(e)}"
        print(error_msg)
        return False, error_msg


"""Update token usage on consumption."""


def update_token_usage_on_consumption(
    bot_id: int, consumed_token, consumed_token_type: str, db: Session
):
    try:
        # Retrieve the bot's token usage data from the database
        bot_token_usage = db.query(TokenUsage).filter_by(bot_id=bot_id).first()

        subordinate_bots = (
            db.query(TokenUsage).filter_by(user_id=bot_token_usage.user_id).all()
        )

        credit = (
            db.query(UserCredits).filter_by(id=bot_token_usage.user_credit_id).first()
        )

        if consumed_token_type == "direct_bot":
            # Update the bot's token usage data
            bot_token_usage.user_request_token += consumed_token.request_token
            bot_token_usage.user_response_token += consumed_token.response_token
            bot_token_usage.open_ai_request_token += (
                consumed_token.open_ai_request_token
            )
            bot_token_usage.open_ai_response_token += (
                consumed_token.open_ai_response_token
            )

        if consumed_token_type == "whatsapp_bot":
            # Update the bot's token usage data
            bot_token_usage.whatsapp_request_tokens += consumed_token.request_token
            bot_token_usage.whatsapp_response_tokens += consumed_token.response_token
            bot_token_usage.open_ai_request_token += (
                consumed_token.open_ai_request_token
            )
            bot_token_usage.open_ai_response_token += (
                consumed_token.open_ai_response_token
            )

        if consumed_token_type == "slack_bot":
            # Update the bot's token usage data
            bot_token_usage.slack_request_tokens += consumed_token.request_token
            bot_token_usage.slack_response_tokens += consumed_token.response_token
            bot_token_usage.open_ai_request_token += (
                consumed_token.open_ai_request_token
            )
            bot_token_usage.open_ai_response_token += (
                consumed_token.open_ai_response_token
            )

        if consumed_token_type == "zapier_bot":
            # Update the bot's token usage data
            bot_token_usage.zapier_request_tokens += consumed_token.request_token
            bot_token_usage.zapier_response_tokens += consumed_token.response_token
            bot_token_usage.open_ai_request_token += (
                consumed_token.open_ai_request_token
            )
            bot_token_usage.open_ai_response_token += (
                consumed_token.open_ai_response_token
            )

        # update all subordinate bots combined token usage data
        consumption_stats = (
            consumed_token.request_token * 0.5
            + consumed_token.response_token * 0.3
            + consumed_token.open_ai_request_token * 0.2
            + consumed_token.open_ai_response_token * 0.5
        )
        for subordinate_bot in subordinate_bots:
            subordinate_bot.combined_token_consumption += consumption_stats
            db.add(subordinate_bot)
            db.flush()

        total_token_consumption = bot_token_usage.combined_token_consumption
        print("total_token_consumption", total_token_consumption)

        credits_consumed = total_token_consumption / credit.token_per_unit
        print("credits_consumed", credits_consumed)

        balance_credits = credit.credits_purchased - credits_consumed
        print("balance_credits", balance_credits)

        credit.credits_consumed = credits_consumed
        credit.credit_balance = balance_credits

        db.add(credit)

        db.commit()
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
        token_limit = user_credits.credits_purchased * user_credits.token_per_unit
        subordinate_bots = db.query(TokenUsage).filter_by(user_id=user_id).all()
        if subordinate_bots:
            combined_token_consumption = subordinate_bots[0].combined_token_consumption
            token_limit = subordinate_bots[0].token_limit

        token_usage = TokenUsage(
            bot_id=bot_id,
            user_id=user_id,
            user_credit_id=user_credits.id,
            token_limit=token_limit,
            combined_token_consumption=combined_token_consumption,
        )
        db.add(token_usage)
        db.commit()

        return True, "Token usage entry created successfully"
    else:
        return False, "User not found, please activate plan"
