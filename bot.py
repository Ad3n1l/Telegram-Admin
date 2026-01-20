import os
import logging
from telegram import Update, constants
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Configuration ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
# Simple in-memory warning tracker {user_id: count}
# Note: This resets if the bot restarts.
user_warnings = {}

# --- Helper Functions ---
async def is_admin(update: Update):
    """Checks if the user sending the message is an admin."""
    if not update.effective_chat or update.effective_chat.type == constants.ChatType.PRIVATE:
        return True
    member = await update.effective_chat.get_member(update.effective_user.id)
    return member.status in [constants.ChatMemberStatus.ADMINISTRATOR, constants.ChatMemberStatus.OWNER]

# --- Bot Features ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    await update.message.reply_text("🛡️ **Moderation Bot Active**\nAdd me to a group and make me admin to start protecting!")

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Greets new members."""
    for new_user in update.message.new_chat_members:
        await update.message.reply_text(f"Welcome {new_user.first_name}! please no links or swearing. 😊")

async def moderate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main moderation logic for links and profanity."""
    if await is_admin(update) or not update.message.text:
        return

    text = update.message.text.lower()
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    
    # Check for links or common bad words
    bad_words = ["fuck", "shit", "bitch"] # Add more as needed
    has_link = "http" in text or "t.me/" in text
    has_profanity = any(word in text for word in bad_words)

    if has_link or has_profanity:
        await update.message.delete()
        
        # Increment warnings
        user_warnings[user_id] = user_warnings.get(user_id, 0) + 1
        count = user_warnings[user_id]
        
        if count >= 3:
            await update.effective_chat.ban_member(user_id)
            await context.bot.send_message(update.effective_chat.id, f"🚫 {name} banned (3/3 warnings).")
            user_warnings[user_id] = 0
        else:
            reason = "Links" if has_link else "Language"
            await context.bot.send_message(
                update.effective_chat.id, 
                f"⚠️ {name}, {reason} not allowed! Warning: {count}/3"
            )

async def reset_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to reset a user's warnings."""
    if not await is_admin(update): return
    user_warnings.clear()
    await update.message.reply_text("✅ All warning counts have been reset.")

# --- Execution ---
if __name__ == '__main__':
    if not TOKEN:
        print("Error: No BOT_TOKEN found!")
        exit(1)

    app = ApplicationBuilder().token(TOKEN).build()
    
    # Register Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset_warnings))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), moderate))
    
    # Railway Settings
    PORT = int(os.getenv("PORT", 8080))
    print(f"Bot starting on port {PORT}...")
    
    # Use Polling for simplicity on Railway Free Tier
    app.run_polling()
