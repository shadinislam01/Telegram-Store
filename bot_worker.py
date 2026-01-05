import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import os
import time
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get bot token from environment
API_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

if not API_TOKEN or API_TOKEN == 'dummy_token_for_testing':
    logger.error("❌ TELEGRAM_BOT_TOKEN is not set in environment variables!")
    logger.error("Please set TELEGRAM_BOT_TOKEN in Render.com environment variables")
    exit(1)

# Create bot instance
bot = telebot.TeleBot(API_TOKEN)

# Get web app URL from environment
WEB_APP_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://your-app.onrender.com')

# Store for user web apps
user_web_apps = {}

# /start command handler
@bot.message_handler(commands=['start'])
def handle_start(message):
    try:
        user = message.from_user
        user_id = user.id
        first_name = user.first_name or "User"
        
        logger.info(f"👤 User {user_id} ({first_name}) started the bot")
        
        # Create web app URL with user ID
        web_app_url = f"{WEB_APP_URL}?tg_user_id={user_id}"
        
        # Create inline keyboard with web app button
        keyboard = InlineKeyboardMarkup()
        web_app_button = InlineKeyboardButton(
            text="🚀 Open Own Bazar",
            web_app=WebAppInfo(url=web_app_url)
        )
        keyboard.add(web_app_button)
        
        # Welcome message
        welcome_text = f"""
✨ *Welcome to Own Bazar, {first_name}!* 🌟

💰 *Earn Credits by watching Ads!*
🛍️ *Buy Premium Accounts & Services*
⚡ *Instant Delivery*

*✨ Features:*
• Watch ads & earn up to 1100+ credits daily
• 4 different ad types with varying rewards
• Premium accounts (VPN, Netflix, Spotify, etc.)
• 24/7 Support

*📱 How to Start:*
1. Click the button below to open the app
2. Watch ads to earn credits
3. Use credits to buy items
4. Get instant delivery!

*🎁 New users get 100 FREE credits!*

Tap the button below to start earning! 👇
        """
        
        bot.send_message(
            message.chat.id,
            welcome_text,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        
        # Store web app URL for this user
        user_web_apps[user_id] = web_app_url
        
    except Exception as e:
        logger.error(f"Error in /start: {e}")
        bot.send_message(
            message.chat.id,
            "❌ Sorry, something went wrong. Please try again."
        )

# /ads command handler
@bot.message_handler(commands=['ads'])
def handle_ads(message):
    user = message.from_user
    user_id = user.id
    
    # Create web app URL for earn section
    web_app_url = f"{WEB_APP_URL}?tg_user_id={user_id}#earn"
    
    keyboard = InlineKeyboardMarkup()
    web_app_button = InlineKeyboardButton(
        text="📺 Watch Ads & Earn",
        web_app=WebAppInfo(url=web_app_url)
    )
    keyboard.add(web_app_button)
    
    ads_text = f"""
📢 *Ad System Information*

*🎯 Ad Types & Rewards:*
• Popup Ads → *+4 credits each*
• Video Ads → *+6 credits each*  
• Interstitial Ads → *+8 credits each*
• Banner Ads → *+3 credits each*

*📊 Daily Limits:*
• Popup Ads: 60/day (240 credits)
• Video Ads: 40/day (240 credits)
• Interstitial Ads: 30/day (240 credits)
• Banner Ads: 100/day (300 credits)
• *Total Potential:* **1020+ credits daily!**

*💡 Tips:*
1. All ads work in mobile browser
2. Close popup ads after viewing
3. Videos play automatically
4. No special requirements needed

Click below to start earning! 👇
    """
    
    bot.send_message(
        message.chat.id,
        ads_text,
        parse_mode='Markdown',
        reply_markup=keyboard
    )

# /earn command handler
@bot.message_handler(commands=['earn'])
def handle_earn(message):
    user = message.from_user
    user_id = user.id
    
    # Create web app URL for earn section
    web_app_url = f"{WEB_APP_URL}?tg_user_id={user_id}#earn"
    
    keyboard = InlineKeyboardMarkup()
    web_app_button = InlineKeyboardButton(
        text="📺 Watch Ads & Earn",
        web_app=WebAppInfo(url=web_app_url)
    )
    keyboard.add(web_app_button)
    
    earn_text = f"""
💰 *Earn Credits Fast!*

*🎯 Ad Types & Rewards:*
• Popup Ads → *+4 credits each*
• Video Ads → *+6 credits each*  
• Interstitial Ads → *+8 credits each*
• Banner Ads → *+3 credits each*

*📊 Daily Limits:*
• Popup Ads: 60/day (240 credits)
• Video Ads: 40/day (240 credits)
• Interstitial Ads: 30/day (240 credits)
• Banner Ads: 100/day (300 credits)
• *Total Potential:* **1020+ credits daily!**

*💡 Tips:*
1. Watch all ad types for maximum earnings
2. Premium ads give highest rewards
3. Take short breaks between ads

Click below to start earning! 👇
    """
    
    bot.send_message(
        message.chat.id,
        earn_text,
        parse_mode='Markdown',
        reply_markup=keyboard
    )

# /shop command handler
@bot.message_handler(commands=['shop'])
def handle_shop(message):
    user = message.from_user
    user_id = user.id
    
    # Create web app URL for shop section
    web_app_url = f"{WEB_APP_URL}?tg_user_id={user_id}#shop"
    
    keyboard = InlineKeyboardMarkup()
    web_app_button = InlineKeyboardButton(
        text="🛍️ Browse Shop",
        web_app=WebAppInfo(url=web_app_url)
    )
    keyboard.add(web_app_button)
    
    shop_text = f"""
🛍️ *Premium Shop*

*🔥 Popular Items:*
• VPN Accounts (FlyVPN, NordVPN, ExpressVPN)
• Streaming (Netflix, YouTube, Disney+)
• Music (Spotify, Apple Music)
• AI Tools (ChatGPT Plus, Midjourney)
• Gaming (Steam, Epic Games)

*⚡ Features:*
• Instant delivery after purchase
• 100% working accounts
• Global access
• 24/7 support

*💰 How to Get Credits:*
1. Watch ads in the Earn section
2. Earn 1000+ credits daily
3. Use credits to buy items

Click below to browse shop! 👇
    """
    
    bot.send_message(
        message.chat.id,
        shop_text,
        parse_mode='Markdown',
        reply_markup=keyboard
    )

# /balance command handler
@bot.message_handler(commands=['balance', 'credits'])
def handle_balance(message):
    user = message.from_user
    user_id = user.id
    
    # Create web app URL
    web_app_url = f"{WEB_APP_URL}?tg_user_id={user_id}"
    
    keyboard = InlineKeyboardMarkup()
    web_app_button = InlineKeyboardButton(
        text="📊 Check Balance",
        web_app=WebAppInfo(url=web_app_url)
    )
    keyboard.add(web_app_button)
    
    balance_text = f"""
💰 *Check Your Balance*

To view your credits and transaction history, please open the web app.

*In the app you can:*
• View current balance
• See earnings history
• Track daily progress
• Check purchase history

Click below to open the app and check your balance! 👇
    """
    
    bot.send_message(
        message.chat.id,
        balance_text,
        parse_mode='Markdown',
        reply_markup=keyboard
    )

# /help command handler
@bot.message_handler(commands=['help', 'support'])
def handle_help(message):
    help_text = """
🆘 *Own Bazar Help Center*

*🤔 How to Use:*
1. Use /start to begin
2. Open the web app using the button
3. Watch ads in the "Earn" section
4. Use credits to buy items in "Shop"

*💰 Earning Credits:*
• Popup Ads: 4 credits each
• Video Ads: 6 credits each  
• Interstitial Ads: 8 credits each
• Banner Ads: 3 credits each
• Daily limits apply for each type

*🛍️ Buying Items:*
1. Browse items in Shop
2. Click "Unlock" to purchase
3. Get account details instantly
4. Use credentials immediately

*❓ Common Questions:*
Q: How do I get more credits?
A: Watch more ads daily! Each type has daily limits.

Q: Are the accounts working?
A: Yes, all accounts are 100% tested and working.

Q: What if I have issues?
A: Contact @shadinislam01 for 24/7 support.

*📞 Support:* @shadinislam01
*⏰ 24/7 Support Available*

*🎯 Commands:*
/start - Open the app
/ads - Ad information
/earn - Watch ads & earn
/shop - Browse items
/balance - Check credits
/help - This message
    """
    
    bot.send_message(
        message.chat.id,
        help_text,
        parse_mode='Markdown'
    )

# Handle any other text messages
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    if message.text:
        # If user sends text, guide them to use commands
        guide_text = """
🤖 *Own Bazar Bot*

I'm here to help you earn credits and shop for premium accounts!

Please use one of these commands:

/start - Open the web app
/ads - Ad information
/earn - Watch ads & earn credits  
/shop - Browse premium items
/balance - Check your credits
/help - Get help & support

Or simply click the menu button to see all commands!
        """
        
        bot.send_message(
            message.chat.id,
            guide_text,
            parse_mode='Markdown'
        )

# Bot polling with error handling and restart
def run_bot():
    logger.info("🤖 Starting Own Bazar Telegram Bot...")
    logger.info(f"🌐 Web App URL: {WEB_APP_URL}")
    
    while True:
        try:
            logger.info("🔄 Starting bot polling...")
            
            # Set bot commands for menu
            bot.set_my_commands([
                telebot.types.BotCommand("start", "Open the app"),
                telebot.types.BotCommand("ads", "Ad information"),
                telebot.types.BotCommand("earn", "Watch ads & earn"),
                telebot.types.BotCommand("shop", "Browse items"),
                telebot.types.BotCommand("balance", "Check credits"),
                telebot.types.BotCommand("help", "Get help")
            ])
            
            # Start polling
            bot.infinity_polling(
                timeout=60,
                long_polling_timeout=60,
                logger_level=logging.INFO
            )
            
        except Exception as e:
            logger.error(f"❌ Bot error: {e}")
            logger.info("🔄 Restarting bot in 10 seconds...")
            time.sleep(10)

if __name__ == '__main__':
    run_bot()
