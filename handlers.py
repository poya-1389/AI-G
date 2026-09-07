import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import database as db
from ai_clients import generate

ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x]

# Conversation states for /newcharacter
NAME, DESCRIPTION, PERSONA = range(3)

WELCOME_TEXT = (
    "سلام! 👋\n\n"
    "من یک ربات هوش مصنوعی با قابلیت کاراکترسازی هستم.\n\n"
    "دستورات اصلی:\n"
    "/newcharacter — ساخت یک کاراکتر جدید\n"
    "/characters — لیست و انتخاب کاراکتر فعال\n"
    "/model — انتخاب مدل هوش مصنوعی (Gemini / DeepSeek / ChatGPT)\n"
    "/reset — پاک کردن حافظه‌ی مکالمه با کاراکتر فعلی\n"
    "/help — راهنما\n\n"
    "بعد از ساختن یا انتخاب یک کاراکتر، فقط پیام بده تا باهاش وارد گفتگو بشی."
)


# ======================= USER COMMANDS =======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.get_or_create_user(user.id, user.username or user.first_name)
    await update.message.reply_text(WELCOME_TEXT)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_TEXT)


async def choose_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Gemini (رایگان)", callback_data="model:gemini")],
        [InlineKeyboardButton("DeepSeek", callback_data="model:deepseek")],
        [InlineKeyboardButton("ChatGPT", callback_data="model:openai")],
    ]
    await update.message.reply_text("کدوم مدل هوش مصنوعی رو می‌خوای استفاده کنی؟", reply_markup=InlineKeyboardMarkup(keyboard))


async def model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    model = query.data.split(":")[1]
    db.set_user_model(query.from_user.id, model)
    await query.edit_message_text(f"✅ مدل فعال شد روی: {model}")


async def list_characters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chars = db.list_user_characters(user_id)
    if not chars:
        await update.message.reply_text("هنوز هیچ کاراکتری نساختی. با /newcharacter یکی بساز.")
        return
    keyboard = [[InlineKeyboardButton(c["name"], callback_data=f"selectchar:{c['character_id']}")] for c in chars]
    await update.message.reply_text("یکی از کاراکترها رو برای گفتگو انتخاب کن:", reply_markup=InlineKeyboardMarkup(keyboard))


async def select_character_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    character_id = int(query.data.split(":")[1])
    db.set_active_character(query.from_user.id, character_id)
    char = db.get_character(character_id)
    await query.edit_message_text(f"✅ حالا داری با «{char['name']}» چت می‌کنی. پیامت رو بفرست!")


async def reset_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_or_create_user(user_id, update.effective_user.username or "")
    if not user["active_character_id"]:
        await update.message.reply_text("هنوز کاراکتری انتخاب نکردی.")
        return
    db.clear_history(user_id, user["active_character_id"])
    await update.message.reply_text("🧹 حافظه‌ی این گفتگو پاک شد.")


# ======================= CHARACTER CREATION =======================

async def new_character_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("بیا یه کاراکتر جدید بسازیم! ✨\n\nاول، اسم کاراکتر چیه؟")
    return NAME


async def new_character_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_char_name"] = update.message.text.strip()
    await update.message.reply_text("عالی. حالا یه توضیح کوتاه (یک خط) درباره‌ی این کاراکتر بنویس.")
    return DESCRIPTION


async def new_character_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_char_description"] = update.message.text.strip()
    await update.message.reply_text(
        "حالا شخصیت رو با جزئیات بیشتر توصیف کن — لحن صحبت، پیش‌زمینه، سبک گفتگو، علایق. "
        "هر چقدر دقیق‌تر بنویسی، نتیجه بهتره."
    )
    return PERSONA


async def new_character_persona(update: Update, context: ContextTypes.DEFAULT_TYPE):
    persona_prompt = update.message.text.strip()
    name = context.user_data.pop("new_char_name")
    description = context.user_data.pop("new_char_description")
    user_id = update.effective_user.id

    character_id = db.create_character(user_id, name, description, persona_prompt, is_public=False)
    db.set_active_character(user_id, character_id)

    await update.message.reply_text(
        f"✅ کاراکتر «{name}» ساخته شد و الان فعاله!\nفقط پیام بده تا باهاش گفتگو کنی. برای دیدن لیست کاراکترها: /characters"
    )
    return ConversationHandler.END


async def cancel_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("ساخت کاراکتر لغو شد.")
    return ConversationHandler.END


async def delete_character_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استفاده: /deletecharacter <شناسه_کاراکتر>")
        return
    try:
        character_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("شناسه‌ی کاراکتر باید عدد باشه.")
        return
    user_id = update.effective_user.id
    ok = db.delete_character(character_id, user_id, is_admin=user_id in ADMIN_IDS)
    await update.message.reply_text("🗑️ کاراکتر حذف شد." if ok else "این کاراکتر پیدا نشد یا مال تو نیست.")


# ======================= MAIN CHAT HANDLER =======================

async def handle_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_or_create_user(user_id, update.effective_user.username or "")

    if db.is_user_banned(user_id):
        await update.message.reply_text("⛔ دسترسی شما به ربات مسدود شده.")
        return

    if db.get_setting("maintenance_mode", "0") == "1" and user_id not in ADMIN_IDS:
        await update.message.reply_text("🛠️ ربات موقتاً برای تعمیرات خاموشه، بعداً امتحان کن.")
        return

    if not user["active_character_id"]:
        await update.message.reply_text("اول باید یه کاراکتر انتخاب کنی یا بسازی.\n/newcharacter برای ساخت، /characters برای انتخاب.")
        return

    if not db.check_and_increment_rate_limit(user_id):
        await update.message.reply_text("امروز به سقف تعداد پیام‌های مجاز رسیدی. فردا دوباره امتحان کن 🙏")
        return

    character = db.get_character(user["active_character_id"])
    if character is None:
        await update.message.reply_text("کاراکتر فعال پیدا نشد، لطفاً یکی دیگه انتخاب کن با /characters")
        return

    history = db.get_history(user_id, character["character_id"])
    user_text = update.message.text

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    reply_text = await generate(
        model_name=user["preferred_model"] or "gemini",
        character_persona_prompt=character["persona_prompt"],
        history=history,
        user_message=user_text,
    )

    db.add_message(user_id, character["character_id"], "user", user_text)
    db.add_message(user_id, character["character_id"], "assistant", reply_text)

    await update.message.reply_text(reply_text)


# ======================= ADMIN PANEL =======================

def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("⛔ این دستور فقط برای ادمین‌هاست.")
            return
        return await func(update, context)
    return wrapper


ADMIN_HELP = (
    "🛠️ پنل ادمین — دستورات:\n\n"
    "/stats — آمار کلی ربات\n"
    "/broadcast <متن> — ارسال پیام همگانی به همه‌ی کاربران\n"
    "/ban <user_id> — مسدود کردن کاربر\n"
    "/unban <user_id> — رفع مسدودیت\n"
    "/setlimit <عدد> — تنظیم سقف پیام روزانه هر کاربر\n"
    "/sethistory <عدد> — تعداد پیام‌های نگه‌داری‌شده در حافظه\n"
    "/setdefaultmodel <gemini|deepseek|openai> — مدل پیش‌فرض کاربران جدید\n"
    "/maintenance <on|off> — حالت تعمیرات\n"
    "/publiccharacter <character_id> — یک کاراکتر رو برای همه عمومی کن"
)


@admin_only
async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ADMIN_HELP)


@admin_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 آمار ربات\n\n"
        f"👥 تعداد کاربران: {db.count_all_users()}\n"
        f"🎭 تعداد کاراکترها: {db.count_all_characters()}\n"
        f"📩 سقف پیام روزانه: {db.get_setting('daily_message_limit')}\n"
        f"🧠 طول حافظه‌ی مکالمه: {db.get_setting('max_history_messages')}\n"
        f"🤖 مدل پیش‌فرض: {db.get_setting('default_model')}\n"
        f"🛠️ حالت تعمیرات: {'روشن' if db.get_setting('maintenance_mode') == '1' else 'خاموش'}"
    )


@admin_only
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استفاده: /broadcast متن پیام")
        return
    text = "📢 " + " ".join(context.args)
    sent, failed = 0, 0
    for uid in db.list_all_user_ids():
        try:
            await context.bot.send_message(chat_id=uid, text=text)
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(f"ارسال شد به {sent} کاربر (ناموفق: {failed})")


@admin_only
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استفاده: /ban <user_id>")
        return
    db.set_ban_status(int(context.args[0]), True)
    await update.message.reply_text(f"⛔ کاربر {context.args[0]} مسدود شد.")


@admin_only
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استفاده: /unban <user_id>")
        return
    db.set_ban_status(int(context.args[0]), False)
    await update.message.reply_text(f"✅ کاربر {context.args[0]} رفع مسدودیت شد.")


@admin_only
async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("استفاده: /setlimit <عدد>")
        return
    db.set_setting("daily_message_limit", context.args[0])
    await update.message.reply_text(f"✅ سقف پیام روزانه روی {context.args[0]} تنظیم شد.")


@admin_only
async def set_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("استفاده: /sethistory <عدد>")
        return
    db.set_setting("max_history_messages", context.args[0])
    await update.message.reply_text(f"✅ طول حافظه روی {context.args[0]} پیام تنظیم شد.")


@admin_only
async def set_default_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    valid = {"gemini", "deepseek", "openai"}
    if not context.args or context.args[0] not in valid:
        await update.message.reply_text("استفاده: /setdefaultmodel <gemini|deepseek|openai>")
        return
    db.set_setting("default_model", context.args[0])
    await update.message.reply_text(f"✅ مدل پیش‌فرض روی {context.args[0]} تنظیم شد.")


@admin_only
async def maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or context.args[0] not in ("on", "off"):
        await update.message.reply_text("استفاده: /maintenance <on|off>")
        return
    db.set_setting("maintenance_mode", "1" if context.args[0] == "on" else "0")
    await update.message.reply_text(f"✅ حالت تعمیرات: {context.args[0]}")


@admin_only
async def make_character_public(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("استفاده: /publiccharacter <character_id>")
        return
    character_id = int(context.args[0])
    char = db.get_character(character_id)
    if not char:
        await update.message.reply_text("کاراکتر پیدا نشد.")
        return
    db.make_character_public(character_id)
    await update.message.reply_text(f"✅ کاراکتر «{char['name']}» برای همه عمومی شد.")
