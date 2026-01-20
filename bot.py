import os
import logging
import re
from telegram import Update, constants
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Configuration ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
user_warnings = {}

# --- Expanded Profanity Library ---
# This set covers variations, leetspeak, and common slurs
PROFANITY_LIBRARY = {
    'fuck', 'fuk', 'fck', 'f u c k', 'phuck', 'fux', 'f0ck',
    'shit', 'sh1t', 'shyt', 'sht', 's h i t',
    'bitch', 'btch', 'biatch', 'b1tch',
    'ass', 'asshole', 'a$$', 'a55', 'arsh',
    'bastard', 'cunt', 'dick', 'cock', 'pussy', 'slut', 'whore',
    'nigger', 'faggot', 'retard', 'dumbass', 'dipshit', 'jackass',
    'mierda', 'puta', 'pendejo', 'cabron', 'verga', 'joder',
    'scheisse', 'fotze', 'schlampe'
    # The code below will check if any of these are INSIDE the message
}

# --- Helper Functions ---
async def is_admin(update: Update):
    if not update.effective_chat or update.effective_chat.type == constants.ChatType.PRIVATE:
        return True
    member = await update.effective_chat.get_member(update.effective_user.id)
    return member.status in [constants.ChatMemberStatus.ADMINISTRATOR, constants.ChatMemberStatus.OWNER]

# --- Bot Features ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛡️ **Moderation Bot Active**\nI'm watching for links and profanity!")

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for new_user in update.message.new_chat_members:
        await update.message.reply_text(f"Welcome {new_user.first_name}! No links or swearing allowed. 😊")

async def moderate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update) or not update.message:
        return

    # Check for text or caption (in case they send a link with a photo)
    content = update.message.text or update.message.caption or ""
    content_lower = content.lower()
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    
    # 1. Advanced Link Detection
    # Checks for raw text links and Telegram "entities" (blue clickable links)
    url_pattern = r'(https?://[^\s]+)|(www\.[^\s]+)|([a-zA-Z0-9-]+\.(com|net|org|me|io|info|tk|ml|ga))'
    has_raw_link = re.search(url_pattern, content_lower)
    has_entity_link = any(e.type in [constants.MessageEntity.URL, constants.MessageEntity.TEXT_LINK] for e in update.message.entities)
    
    # 2. Profanity Detection (Case-insensitive)
    has_profanity = any(word in content_lower for word in PROFANITY_LIBRARY)

    if has_raw_link or has_entity_link or has_profanity:
        try:
            await update.message.delete()
            
            user_warnings[user_id] = user_warnings.get(user_id, 0) + 1
            count = user_warnings[user_id]
            
            reason = "Links" if (has_raw_link or has_entity_link) else "Language"
            
            if count >= 3:
                await update.effective_chat.ban_member(user_id)
                await context.bot.send_message(update.effective_chat.id, f"🚫 {name} banned (3/3 warnings for {reason}).")
                user_warnings[user_id] = 0
            else:
                await context.bot.send_message(
                    update.effective_chat.id, 
                    f"⚠️ {name}, {reason} are not allowed!\nWarning: {count}/3"
                )
        except Exception as e:
            logger.error(f"Failed to delete or ban: {e}")

async def reset_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update): return
    user_warnings.clear()
    await update.message.reply_text("✅ All warnings reset.")

# --- Execution ---
if __name__ == '__main__':
    if not TOKEN:
        exit(1)

    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset_warnings))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    # This filter now catches text AND captions on photos/videos
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & (~filters.COMMAND), moderate))
    
    PORT = int(os.getenv("PORT", 8080))
    app.run_polling()
