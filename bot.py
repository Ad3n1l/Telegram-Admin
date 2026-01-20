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

# --- MEGA Profanity Library ---
PROFANITY_LIBRARY = {
    'fuck', 'fuk', 'fck', 'phuck', 'fux', 'f0ck', 'f u c k', 'f.u.c.k',
    'shit', 'sh1t', 'shyt', 'sht', 's h i t', 's.h.i.t',
    'bitch', 'btch', 'biatch', 'b1tch', 'b!tch',
    'ass', 'asshole', 'a$$', 'a55', 'arsh', 'butt',
    'bastard', 'cunt', 'dick', 'cock', 'pussy', 'slut', 'whore', 'cum',
    'nigger', 'faggot', 'retard', 'dumbass', 'dipshit', 'jackass', 'moron',
    'mierda', 'puta', 'pendejo', 'cabron', 'verga', 'joder', 'chinga',
    'scheisse', 'fotze', 'schlampe', 'hurensohn', 'nigga', 'stfu', 'wtf'
}

# --- Helper Functions ---
async def is_admin(update: Update):
    if not update.effective_chat or update.effective_chat.type == constants.ChatType.PRIVATE:
        return True
    member = await update.effective_chat.get_member(update.effective_user.id)
    return member.status in [constants.ChatMemberStatus.ADMINISTRATOR, constants.ChatMemberStatus.OWNER]

# --- Bot Features ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛡️ **Moderation Bot Active**\nI'm watching for links and slurs. Admins can use /warn (by reply) and /reset.")

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for new_user in update.message.new_chat_members:
        await update.message.reply_text(f"Welcome {new_user.first_name}! No links or swearing allowed. 😊")

# Manual Warn Command
async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Please use /warn by replying to the user's message.")
        return

    target_user = update.message.reply_to_message.from_user
    user_id = target_user.id
    name = target_user.first_name
    
    target_member = await update.effective_chat.get_member(user_id)
    if target_member.status in [constants.ChatMemberStatus.ADMINISTRATOR, constants.ChatMemberStatus.OWNER]:
        await update.message.reply_text("❌ I cannot warn another admin.")
        return

    user_warnings[user_id] = user_warnings.get(user_id, 0) + 1
    count = user_warnings[user_id]
    
    await update.message.reply_to_message.delete()
    
    if count >= 3:
        await update.effective_chat.ban_member(user_id)
        await context.bot.send_message(update.effective_chat.id, f"🚫 {name} has been banned after 3 warnings.")
        user_warnings[user_id] = 0
    else:
        await context.bot.send_message(update.effective_chat.id, f"⚠️ {name} has been warned by an admin. Warning: {count}/3")

async def moderate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update) or not update.message:
        return

    content = update.message.text or update.message.caption or ""
    content_lower = content.lower()
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    
    # 1. THE NUCLEAR LINK FILTER (Captures almost all domains)
    url_pattern = r'(https?://\S+)|(www\.\S+)|(t\.me/\S+)|([\w-]+\.(com|net|org|me|io|info|tk|ml|ga|co|xyz|online|biz|uk|us|ca|gov|edu|shop|link|top|click))'
    has_raw_link = re.search(url_pattern, content_lower)
    
    # 2. Check Telegram Entities (Handles blue links and hidden [Hyperlinks])
    has_entity_link = False
    if update.message.entities:
        for entity in update.message.entities:
            if entity.type in [constants.MessageEntity.URL, constants.MessageEntity.TEXT_LINK]:
                has_entity_link = True
                break
    
    # 3. Profanity Detection (Case-insensitive)
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
                await context.bot.send_message(update.effective_chat.id, f"⚠️ {name}, {reason} are not allowed!\nWarning: {count}/3")
        except Exception as e:
            logger.error(f"Moderation failed: {e}")

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
    app.add_handler(CommandHandler("warn", warn_user))
    
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    # Note: Use filters.TEXT | filters.CAPTION to catch links in image descriptions
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & (~filters.COMMAND), moderate))
    
    PORT = int(os.getenv("PORT", 8080))
    app.run_polling()
