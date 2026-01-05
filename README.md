# Own Bazar - Earn & Shop Platform
=====================

A complete earn-and-shop platform where users can earn credits by watching ads and spend them on premium accounts and services.

## Features
--------

### For Users
- **Earn Credits**: Watch 4 types of ads (Popup, Video, Interstitial, Banner)
- **Shop**: Buy premium accounts (VPN, Netflix, Spotify, etc.)
- **Dashboard**: View earnings, spending, and statistics
- **History**: Track all transactions
- **My Purchases**: Access purchased items anytime
- **Instant Delivery**: Get account details immediately after purchase

### For Admins
- **Admin Panel**: Complete system management
- **User Management**: Add/remove credits, reset ads
- **Item Management**: Add/edit/delete shop items
- **Ad Control**: Configure ad rewards and limits
- **Statistics**: Detailed system analytics
- **System Tools**: Backup, SQL tool, configuration

## Quick Start
------------

### Prerequisites
- Python 3.8+
- Telegram Bot Token
- Render.com account (for deployment)

### Local Installation

1. Create project folder:
```
mkdir own-bazar
cd own-bazar
```

2. Create required files:
- index.html (main web interface)
- app.py (Flask application)
- bot_worker.py (Telegram bot)
- requirements.txt (Python dependencies)
- .env (environment variables)

3. Install dependencies:
```
pip install Flask==2.3.3 Flask-CORS==4.0.0 python-dotenv==1.0.0 pyTelegramBotAPI==4.14.0 gunicorn==20.1.0
```

4. Configure environment variables (.env file):
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
ADMIN_ID=6068468333
ADMIN_PASSWORD=admin123
SECRET_KEY=your_secret_key_here
RENDER_EXTERNAL_URL=https://your-app.onrender.com
PORT=5000
```

5. Run the application:
```
# Terminal 1: Flask server
python app.py

# Terminal 2: Telegram bot
python bot_worker.py
```

### Deployment on Render

1. Create new Web Service on Render.com
2. Connect GitHub repository
3. Configure environment variables:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   ADMIN_ID=6068468333
   ADMIN_PASSWORD=admin123
   SECRET_KEY=your_secret_key_here
   RENDER_EXTERNAL_URL=https://your-app.onrender.com
   ```

4. Build Command:
   ```
   pip install -r requirements.txt
   ```

5. Start Command:
   ```
   gunicorn app:app
   ```

6. Add Background Worker for Telegram Bot:
   - Service Type: Background Worker
   - Start Command: `python bot_worker.py`

## Project Structure
-----------------
```
own-bazar/
├── app.py              # Main Flask application
├── bot_worker.py       # Telegram bot worker
├── requirements.txt    # Python dependencies
├── .env               # Environment variables
└── bot_database.db    # SQLite database (auto-generated)
```

## Ad System
----------

| Ad Type           | Reward | Daily Limit | Potential Daily |
|-------------------|--------|-------------|-----------------|
| Popup Ads         | 4      | 60          | 240 credits     |
| Video Ads         | 6      | 40          | 240 credits     |
| Interstitial Ads  | 8      | 30          | 240 credits     |
| Banner Ads        | 3      | 100         | 300 credits     |
| **Total**         | **-**  | **-**       | **1020+ credits** |

## Available Items
---------------

- VPN Accounts: FlyVPN, NordVPN, ExpressVPN
- Streaming: Netflix, YouTube Premium, Disney+
- Music: Spotify, Apple Music
- AI Tools: ChatGPT Plus, Midjourney
- Gaming: Steam, Epic Games
- And more...

## Telegram Bot Commands
---------------------

- /start   - Open the web app
- /ads     - Ad information
- /earn    - Watch ads & earn credits
- /shop    - Browse items
- /balance - Check credits
- /help    - Get help & support

## Configuration
-------------

### Environment Variables (.env file)
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
ADMIN_ID=6068468333
ADMIN_PASSWORD=admin123
SECRET_KEY=your_secret_key_here
RENDER_EXTERNAL_URL=https://your-app.onrender.com
PORT=5000
```

## Security Features
-----------------

- Admin Authentication: Password-protected admin panel
- SQL Injection Protection: Parameterized queries
- Rate Limiting: Cooldown between ads
- Daily Limits: Prevents abuse of ad system
- User Validation: Ensures users own purchased items

## API Endpoints
-------------

### Public APIs
- GET    /api/user/{uid}       - Get user data
- POST   /api/earn             - Process ad rewards
- GET    /api/items            - Get shop items
- POST   /api/buy              - Purchase item
- GET    /api/history/{uid}    - Get transaction history
- GET    /api/purchases/{uid}  - Get purchased items

### Admin APIs (Requires Authentication)
- POST   /api/admin/login      - Admin login
- POST   /api/admin/manage     - All admin operations
- GET    /api/admin/dashboard  - Admin dashboard data

## Troubleshooting
---------------

### Common Issues

1. Bot not responding:
   - Check TELEGRAM_BOT_TOKEN in .env file
   - Verify bot is started with python bot_worker.py
   - Check Render logs for errors

2. Database errors:
   - Ensure write permissions in deployment
   - Check if database file is created
   - Verify SQLite is supported

3. Ads not loading:
   - Check ad network scripts
   - Verify internet connectivity
   - Check browser console for errors

4. Admin panel not accessible:
   - Verify admin credentials in .env
   - Check if user has admin privileges
   - Clear browser cache

## Usage Instructions
-----------------

### For Users:
1. Go to Telegram bot
2. Type /start command
3. Web app will open
4. Watch ads to earn credits
5. Buy items from Shop

### For Admins:
1. Telegram User ID: 6068468333 (default)
2. Password: admin123 (default)
3. Open Admin Panel
4. Use all management tools

## Contact
-------
For any problems or help, contact on Telegram:
@shadinislam01
Email: bdshadhin121@gmail.com

24/7 Support Available

## License
-------
This project is licensed under the MIT License.

## Support
-------
Give a star if this project helped you!

Built with ❤️ by the Own Bazar Team

---
**Now your Own Bazar platform is completely ready!**
