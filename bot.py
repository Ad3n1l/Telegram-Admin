 #!/usr/bin/env python3
"""
Advanced Telegram Group Moderation Bot
Features: Welcome messages, link filtering, profanity detection, warnings system, and more
"""

import asyncio
import logging
import os
import sys
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Set
import json
import aiohttp
from aiohttp import web
from collections import defaultdict

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Comprehensive profanity list (case-insensitive)
PROFANITY_LIST = {
    # Common profanity
    'fuck', 'shit', 'bitch', 'ass', 'damn', 'hell', 'crap', 'dick', 'cock', 'pussy',
    'bastard', 'asshole', 'motherfucker', 'fucker', 'bullshit', 'piss', 'cunt', 'whore',
    'slut', 'fag', 'nigger', 'retard', 'idiot', 'moron', 'dumbass', 'dipshit', 'jackass',
    # Variations and leetspeak
    'f*ck', 'sh*t', 'b*tch', 'a$$', 'd*mn', 'fuk', 'fck', 'sht', 'btch', 'azz',
    'phuck', 'shyt', 'biatch', 'a55', 'fucc', 'shiit', 'fokk', 'f u c k', 's h i t',
    # International profanity (add your language)
    'puta', 'mierda', 'pendejo', 'cabron', 'chinga', 'verga', 'joder',
    'scheisse', 'arsch', 'fotze', 'schlampe', 'hurensohn',
    # Add more as needed
}

# URL patterns
URL_PATTERN = re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    r'|(?:www\.)[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}'
    r'|(?:t\.me/|telegram\.me/)[a-zA-Z0-9_]+'
)

class UserWarnings:
    """Track user warnings"""
    def __init__(self):
        self.warnings: Dict[int, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        # Format: {chat_id: {user_id: warning_count}}
    
    def add_warning(self, chat_id: int, user_id: int) -> int:
        """Add warning and return total count"""
        self.warnings[chat_id][user_id] += 1
        return self.warnings[chat_id][user_id]
    
    def get_warnings(self, chat_id: int, user_id: int) -> int:
        """Get warning count for user"""
        return self.warnings[chat_id][user_id]
    
    def reset_warnings(self, chat_id: int, user_id: int):
        """Reset warnings for user"""
        self.warnings[chat_id][user_id] = 0

class TelegramBot:
    def __init__(self, token: str, webhook_url: str = None, use_webhook: bool = True):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{8004304094:AAHLjp64dwwSbWfZ3YaVZqEwjtF7N9Laxgg}"
        self.webhook_url = webhook_url
        self.use_webhook = use_webhook
        self.last_update_id = 0
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False
        self.app = web.Application()
        self.user_warnings = UserWarnings()
        self.admin_cache: Dict[int, Set[int]] = {}  # {chat_id: set(admin_user_ids)}
        self.setup_routes()
        
    def setup_routes(self):
        """Setup web routes"""
        self.app.router.add_post('/webhook', self.handle_webhook)
        self.app.router.add_get('/', self.health_check)
        self.app.router.add_get('/health', self.health_check)
        
    async def health_check(self, request):
        """Health check endpoint"""
        return web.json_response({
            'status': 'ok',
            'bot': 'running',
            'timestamp': datetime.now().isoformat(),
            'mode': 'webhook' if self.use_webhook else 'polling',
            'features': ['moderation', 'warnings', 'link_filter', 'profanity_filter']
        })
        
    async def handle_webhook(self, request):
        """Handle incoming webhook updates"""
        try:
            update = await request.json()
            logger.info(f"Received webhook update: {update.get('update_id')}")
            await self.process_update(update)
            return web.json_response({'ok': True})
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return web.json_response({'ok': False, 'error': str(e)}, status=500)
        
    async def start(self):
        """Initialize the bot session"""
        self.session = aiohttp.ClientSession()
        self.running = True
        
        if self.use_webhook and self.webhook_url:
            await self.set_webhook()
        else:
            await self.delete_webhook()
            
        logger.info("Bot started successfully!")
        
    async def stop(self):
        """Clean shutdown"""
        self.running = False
        if self.use_webhook:
            await self.delete_webhook()
        if self.session:
            await self.session.close()
        logger.info("Bot stopped")
        
    async def make_request(self, method: str, params: dict = None):
        """Make API request to Telegram"""
        if not self.session:
            return None
            
        url = f"{self.base_url}/{method}"
        try:
            async with self.session.post(url, json=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    text = await response.text()
                    logger.error(f"API error {response.status}: {text}")
                    return None
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None
    
    async def set_webhook(self):
        """Set webhook URL"""
        webhook_endpoint = f"{self.webhook_url}/webhook"
        params = {'url': webhook_endpoint}
        result = await self.make_request('setWebhook', params)
        if result and result.get('ok'):
            logger.info(f"Webhook set to: {webhook_endpoint}")
        return result
    
    async def delete_webhook(self):
        """Delete webhook"""
        result = await self.make_request('deleteWebhook')
        if result and result.get('ok'):
            logger.info("Webhook deleted")
        return result
    
    async def get_updates(self):
        """Get updates from Telegram (polling mode)"""
        params = {
            'offset': self.last_update_id + 1,
            'timeout': 30,
            'limit': 100
        }
        return await self.make_request('getUpdates', params)
    
    async def send_message(self, chat_id: int, text: str, 
                          parse_mode: str = None, 
                          reply_to_message_id: int = None):
        """Send a message"""
        params = {
            'chat_id': chat_id,
            'text': text
        }
        if parse_mode:
            params['parse_mode'] = parse_mode
        if reply_to_message_id:
            params['reply_to_message_id'] = reply_to_message_id
            
        return await self.make_request('sendMessage', params)
    
    async def delete_message(self, chat_id: int, message_id: int):
        """Delete a message"""
        params = {
            'chat_id': chat_id,
            'message_id': message_id
        }
        return await self.make_request('deleteMessage', params)
    
    async def kick_chat_member(self, chat_id: int, user_id: int):
        """Kick a user from the chat"""
        params = {
            'chat_id': chat_id,
            'user_id': user_id
        }
        return await self.make_request('banChatMember', params)
    
    async def get_chat_administrators(self, chat_id: int):
        """Get list of chat administrators"""
        params = {'chat_id': chat_id}
        return await self.make_request('getChatAdministrators', params)
    
    async def is_admin(self, chat_id: int, user_id: int) -> bool:
        """Check if user is admin"""
        # Update cache if not present
        if chat_id not in self.admin_cache:
            result = await self.get_chat_administrators(chat_id)
            if result and result.get('ok'):
                admins = result.get('result', [])
                self.admin_cache[chat_id] = {admin['user']['id'] for admin in admins}
        
        return user_id in self.admin_cache.get(chat_id, set())
    
    def contains_profanity(self, text: str) -> bool:
        """Check if text contains profanity (case-insensitive)"""
        text_lower = text.lower()
        # Remove spaces between letters (to catch "f u c k")
        text_nospace = re.sub(r'\s+', '', text_lower)
        
        for word in PROFANITY_LIST:
            # Check normal text
            if word in text_lower:
                return True
            # Check without spaces
            if word in text_nospace:
                return True
            # Check as whole words
            pattern = r'\b' + re.escape(word) + r'\b'
            if re.search(pattern, text_lower):
                return True
        
        return False
    
    def contains_url(self, text: str) -> bool:
        """Check if text contains URLs"""
        return URL_PATTERN.search(text) is not None
    
    async def handle_new_member(self, message):
        """Welcome new members"""
        chat_id = message['chat']['id']
        new_members = message.get('new_chat_members', [])
        
        for member in new_members:
            if member.get('is_bot'):
                continue
            
            username = member.get('username', member.get('first_name', 'User'))
            welcome_msg = f"""
🎉 Welcome to the group, {username}!

📋 Please remember:
• Be respectful to all members
• No spam or advertising
• Only admins can post links
• Keep it clean - profanity is not allowed
• You get 3 warnings before removal

Enjoy your stay! 😊
"""
            await self.send_message(chat_id, welcome_msg)
    
    async def handle_link_message(self, message):
        """Handle messages containing links"""
        chat_id = message['chat']['id']
        user_id = message['from']['id']
        message_id = message['message_id']
        user = message['from']
        username = user.get('username', user.get('first_name', 'User'))
        
        # Check if user is admin
        if await self.is_admin(chat_id, user_id):
            return  # Admins can post links
        
        # Delete the message
        await self.delete_message(chat_id, message_id)
        
        # Add warning
        warning_count = self.user_warnings.add_warning(chat_id, user_id)
        
        if warning_count >= 3:
            # Kick user
            await self.kick_chat_member(chat_id, user_id)
            await self.send_message(
                chat_id,
                f"⛔ {username} has been removed for posting links after 3 warnings."
            )
            self.user_warnings.reset_warnings(chat_id, user_id)
        else:
            # Send warning
            await self.send_message(
                chat_id,
                f"⚠️ {username}, only admins can post links!\n"
                f"Warning {warning_count}/3. Next violation will result in removal."
            )
    
    async def handle_profanity_message(self, message):
        """Handle messages containing profanity"""
        chat_id = message['chat']['id']
        user_id = message['from']['id']
        message_id = message['message_id']
        user = message['from']
        username = user.get('username', user.get('first_name', 'User'))
        
        # Check if user is admin
        if await self.is_admin(chat_id, user_id):
            return  # Give admins a pass (optional - remove this if admins should also be moderated)
        
        # Delete the message
        await self.delete_message(chat_id, message_id)
        
        # Add warning
        warning_count = self.user_warnings.add_warning(chat_id, user_id)
        
        if warning_count >= 3:
            # Kick user
            await self.kick_chat_member(chat_id, user_id)
            await self.send_message(
                chat_id,
                f"⛔ {username} has been removed for inappropriate language after 3 warnings."
            )
            self.user_warnings.reset_warnings(chat_id, user_id)
        else:
            # Send warning
            await self.send_message(
                chat_id,
                f"⚠️ {username}, please keep the chat clean!\n"
                f"Warning {warning_count}/3. Next violation will result in removal."
            )
    
    async def handle_command(self, message):
        """Handle bot commands"""
        chat_id = message['chat']['id']
        text = message.get('text', '')
        user = message.get('from', {})
        user_id = user.get('id')
        username = user.get('username', user.get('first_name', 'User'))
        
        if text.startswith('/start'):
            welcome_msg = f"👋 Hello {username}!\n\nI'm a group moderation bot!\n\n🛡️ Features:\n• Welcome new members\n• Filter inappropriate links\n• Detect profanity\n• 3-strike warning system\n• Auto-kick troublemakers\n\nCommands:\n/help - Show help\n/rules - Show group rules\n/warnings - Check your warnings\n/stats - Group statistics (admin only)"
            await self.send_message(chat_id, welcome_msg)
            
        elif text.startswith('/help'):
            help_msg = """🤖 Moderation Bot Help

📋 User Commands:
/rules - View group rules
/warnings - Check your warning count
/help - Show this message

👮 Admin Commands:
/stats - View group statistics
/resetwarnings @username - Reset user warnings
/addword <word> - Add word to filter
/removeword <word> - Remove word from filter

🛡️ Auto-Moderation:
• Links are only allowed from admins
• Profanity is automatically detected
• 3 warnings = automatic removal
• New members get welcome message"""
            await self.send_message(chat_id, help_msg)
            
        elif text.startswith('/rules'):
            rules_msg = """📋 Group Rules

1️⃣ Be respectful to all members
2️⃣ No spam or advertising
3️⃣ Links are only allowed from admins
4️⃣ Keep language clean and appropriate
5️⃣ No personal attacks or harassment
6️⃣ Stay on topic
7️⃣ Three strikes and you're out!

⚠️ Violations result in warnings. 3 warnings = removal."""
            await self.send_message(chat_id, rules_msg)
            
        elif text.startswith('/warnings'):
            warnings = self.user_warnings.get_warnings(chat_id, user_id)
            await self.send_message(
                chat_id,
                f"⚠️ {username}, you have {warnings}/3 warnings.\n"
                f"{'Stay clean to avoid removal!' if warnings > 0 else 'Keep up the good behavior! 👍'}"
            )
            
        elif text.startswith('/stats'):
            if await self.is_admin(chat_id, user_id):
                total_warnings = sum(self.user_warnings.warnings.get(chat_id, {}).values())
                users_with_warnings = len(self.user_warnings.warnings.get(chat_id, {}))
                
                stats_msg = f"""📊 Group Statistics

⚠️ Total warnings issued: {total_warnings}
👥 Users with warnings: {users_with_warnings}
🛡️ Profanity words blocked: {len(PROFANITY_LIST)}
🔗 Link protection: Active
👋 Welcome messages: Active"""
                await self.send_message(chat_id, stats_msg)
            else:
                await self.send_message(chat_id, "❌ This command is only for administrators.")
        
        elif text.startswith('/resetwarnings'):
            if await self.is_admin(chat_id, user_id):
                # Extract username from command (simplified - in production use proper parsing)
                await self.send_message(chat_id, "⚠️ Use: Reply to a user's message with /resetwarnings")
            else:
                await self.send_message(chat_id, "❌ This command is only for administrators.")
    
    async def process_update(self, update):
        """Process a single update"""
        try:
            # Handle new members
            if 'message' in update and 'new_chat_members' in update['message']:
                await self.handle_new_member(update['message'])
                return
            
            # Handle regular messages
            if 'message' in update:
                message = update['message']
                text = message.get('text', '')
                chat_type = message.get('chat', {}).get('type')
                
                # Only moderate in groups/supergroups
                if chat_type not in ['group', 'supergroup']:
                    if text.startswith('/'):
                        await self.handle_command(message)
                    return
                
                # Check for commands first
                if text.startswith('/'):
                    await self.handle_command(message)
                    return
                
                # Check for profanity
                if self.contains_profanity(text):
                    await self.handle_profanity_message(message)
                    return
                
                # Check for links
                if self.contains_url(text):
                    await self.handle_link_message(message)
                    return
                
        except Exception as e:
            logger.error(f"Error processing update: {e}")
    
    async def polling_loop(self):
        """Main polling loop"""
        logger.info("Starting polling mode...")
        while self.running:
            try:
                result = await self.get_updates()
                if not result or not result.get('ok'):
                    await asyncio.sleep(1)
                    continue
                    
                updates = result.get('result', [])
                for update in updates:
                    self.last_update_id = update['update_id']
                    await self.process_update(update)
                    
                if not updates:
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(5)

async def start_bot():
    """Initialize and start the bot"""
    token = os.getenv('BOT_TOKEN')
    webhook_url = os.getenv('WEBHOOK_URL')
    port = int(os.getenv('PORT', 10000))
    use_webhook = os.getenv('USE_WEBHOOK', 'true').lower() == 'true'
    
    if not token:
        logger.error("BOT_TOKEN environment variable not set!")
        sys.exit(1)
    
    bot = TelegramBot(token, webhook_url, use_webhook)
    await bot.start()
    
    # Run web server
    runner = web.AppRunner(bot.app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"🤖 Moderation bot started on port {port}")
    logger.info(f"🛡️ Features: Link filter, Profanity detector, Warning system")
    
    if not use_webhook:
        asyncio.create_task(bot.polling_loop())
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await bot.stop()
        await runner.cleanup()

if __name__ == "__main__":
    logger.info("🚀 Starting Advanced Moderation Bot...")
    
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)