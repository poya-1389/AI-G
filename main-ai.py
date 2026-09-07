import os
import logging

from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters,
)

import database as db
import handlers as h

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
PORT = int(os.getenv("PORT", "10000"))


def build_app() -> Application:
    db.init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # user commands
    app.add_handler(CommandHandler("start", h.start))
    app.add_handler(CommandHandler("help", h.help_cmd))
    app.add_handler(CommandHandler("model", h.choose_model))
    app.add_handler(CommandHandler("characters", h.list_characters))
    app.add_handler(CommandHandler("reset", h.reset_history))
    app.add_handler(CommandHandler("deletecharacter", h.delete_character_cmd))
    app.add_handler(CallbackQueryHandler(h.model_callback, pattern=r"^model:"))
    app.add_handler(CallbackQueryHandler(h.select_character_callback, pattern=r"^selectchar:"))

    # character creation conversation
    creation_conv = ConversationHandler(
        entry_points=[CommandHandler("newcharacter", h.new_character_start)],
        states={
            h.NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, h.new_character_name)],
            h.DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, h.new_character_description)],
            h.PERSONA: [MessageHandler(filters.TEXT & ~filters.COMMAND, h.new_character_persona)],
        },
        fallbacks=[CommandHandler("cancel", h.cancel_creation)],
    )
    app.add_handler(creation_conv)

    # admin panel
    app.add_handler(CommandHandler("admin", h.admin_help))
    app.add_handler(CommandHandler("stats", h.stats))
    app.add_handler(CommandHandler("broadcast", h.broadcast))
    app.add_handler(CommandHandler("ban", h.ban_user))
    app.add_handler(CommandHandler("unban", h.unban_user))
    app.add_handler(CommandHandler("setlimit", h.set_limit))
    app.add_handler(CommandHandler("sethistory", h.set_history))
    app.add_handler(CommandHandler("setdefaultmodel", h.set_default_model))
    app.add_handler(CommandHandler("maintenance", h.maintenance))
    app.add_handler(CommandHandler("publiccharacter", h.make_character_public))

    # plain chat messages (must be added LAST)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, h.handle_chat_message))

    return app


def main():
    app = build_app()
    if WEBHOOK_URL:
        logger.info("Starting in WEBHOOK mode at %s", WEBHOOK_URL)
        app.run_webhook(
            listen="0.0.0.0", port=PORT, url_path=BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
        )
    else:
        logger.info("Starting in POLLING mode (no WEBHOOK_URL set)")
        app.run_polling()


if __name__ == "__main__":
    main()
