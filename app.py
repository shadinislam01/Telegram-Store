import sqlite3
import os
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import time
import logging
from dotenv import load_dotenv
import hashlib
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
ADMIN_ONLY_ID = int(os.environ.get('ADMIN_ID', '6068468333'))
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
WEB_APP_URL = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')

app = Flask(__name__)
CORS(app, resources={
    r"/*": {
        "origins": ["*"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})
app.secret_key = SECRET_KEY

# Rate limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Cache for performance
cache = {}
CACHE_TTL = 30  # seconds

# Thread pool for async operations
executor = ThreadPoolExecutor(max_workers=10)

DB_NAME = 'bot_database.db'

# Ad Networks Configuration with fallbacks
AD_NETWORKS = {
    'popup': {'reward': 4, 'daily_limit': 60, 'type': 'popup'},
    'video': {'reward': 6, 'daily_limit': 40, 'type': 'video'},
    'interstitial': {'reward': 8, 'daily_limit': 30, 'type': 'interstitial'},
    'banner': {'reward': 3, 'daily_limit': 100, 'type': 'banner'},
    'rewarded': {'reward': 10, 'daily_limit': 20, 'type': 'rewarded'}  # Backup
}

# Database functions with connection pooling
class Database:
    _instance = None
    _connection = None
    
    @classmethod
    def get_connection(cls):
        if cls._connection is None:
            cls._connection = sqlite3.connect(DB_NAME, check_same_thread=False)
            cls._connection.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            cls._connection.execute("PRAGMA journal_mode=WAL")
            cls._connection.execute("PRAGMA synchronous=NORMAL")
            cls._connection.execute("PRAGMA cache_size=10000")
            cls._connection.execute("PRAGMA busy_timeout=5000")
        return cls._connection
    
    @classmethod
    def close_connection(cls):
        if cls._connection:
            cls._connection.close()
            cls._connection = None

def get_db():
    return Database.get_connection()

def init_db():
    conn = get_db()
    
    # Users table with indexes
    conn.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        credits INTEGER DEFAULT 100,
        total_earned INTEGER DEFAULT 0,
        total_spent INTEGER DEFAULT 0,
        ads_today INTEGER DEFAULT 0,
        cnt_popup INTEGER DEFAULT 0,
        cnt_video INTEGER DEFAULT 0,
        cnt_interstitial INTEGER DEFAULT 0,
        cnt_banner INTEGER DEFAULT 0,
        cnt_rewarded INTEGER DEFAULT 0,
        purchases INTEGER DEFAULT 0,
        last_ad_date TEXT,
        last_ad_time TEXT,
        is_admin INTEGER DEFAULT 0,
        referral_code TEXT UNIQUE,
        referred_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create indexes
    conn.execute('CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_users_credits ON users(credits)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_users_admin ON users(is_admin)')
    
    # Items table
    conn.execute('''
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT,
        price INTEGER,
        sold INTEGER DEFAULT 0,
        stock INTEGER DEFAULT 999,
        is_active INTEGER DEFAULT 1,
        content TEXT,
        ip TEXT DEFAULT 'Global',
        link TEXT DEFAULT 'N/A',
        tags TEXT,
        priority INTEGER DEFAULT 0,
        discount INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.execute('CREATE INDEX IF NOT EXISTS idx_items_category ON items(category)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_items_price ON items(price)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_items_active ON items(is_active)')
    
    # History table
    conn.execute('''
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        item_name TEXT,
        price INTEGER,
        date TEXT,
        type TEXT,
        item_content TEXT,
        item_ip TEXT,
        item_link TEXT,
        item_category TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.execute('CREATE INDEX IF NOT EXISTS idx_history_user ON history(user_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_history_created ON history(created_at)')
    
    # Config table
    conn.execute('''
    CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT,
        description TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Insert default config
    defaults = []
    for ad_type, config in AD_NETWORKS.items():
        defaults.append((f'reward_{ad_type}', str(config['reward']), f'Reward for {ad_type} ads'))
        defaults.append((f'limit_{ad_type}', str(config['daily_limit']), f'Daily limit for {ad_type} ads'))
    
    defaults.extend([
        ('welcome_bonus', '100', 'Welcome bonus for new users'),
        ('referral_bonus', '50', 'Bonus for referrals'),
        ('ad_cooldown', '5', 'Cooldown between ads in seconds'),
        ('max_ads_daily', '250', 'Maximum total ads per day'),
        ('min_withdraw', '500', 'Minimum credits for withdrawal'),
        ('version', '3.0.0', 'System version'),
        ('maintenance_mode', '0', 'Maintenance mode'),
        ('telegram_bot_url', 'https://t.me/ownbazar_bot', 'Telegram bot URL')
    ])
    
    for key, value, desc in defaults:
        conn.execute(
            'INSERT OR IGNORE INTO config (key, value, description) VALUES (?, ?, ?)',
            (key, value, desc)
        )
    
    # Insert sample items if empty
    if conn.execute('SELECT COUNT(*) FROM items').fetchone()[0] == 0:
        sample_items = [
            ('Bin FlyVPN Premium', 'VPN', 50, 12, 50, 1, 
             'Username: premium_user\nPassword: flyvpn123\nExpiry: 30 days',
             'USA', 'flyvpn.com', 'VPN,Premium,USA', 1, 0),
            
            ('Netflix Premium 4K', 'Streaming', 80, 8, 25, 1,
             'Email: netflix@account.com\nPassword: netflix123\nProfile: 4K Ultra HD',
             'USA', 'netflix.com', 'Streaming,Premium,USA', 2, 10),
            
            ('Spotify Premium', 'Music', 70, 10, 35, 1,
             'Username: spotify_user\nPassword: music2024\nFamily Plan: Yes',
             'Global', 'spotify.com', 'Music,Premium,Global', 3, 0),
            
            ('YouTube Premium', 'Streaming', 60, 15, 40, 1,
             'Email: youtube@premium.com\nPassword: youtube123\nNo Ads: Yes',
             'Global', 'youtube.com', 'Streaming,Music,Global', 4, 5),
            
            ('ChatGPT Plus', 'AI', 100, 5, 30, 1,
             'Email: chatgpt@openai.com\nPassword: ai12345\nGPT-4: Available',
             'Global', 'openai.com', 'AI,ChatGPT,Global', 5, 0)
        ]
        
        conn.executemany('''
            INSERT INTO items (name, category, price, sold, stock, is_active, content, ip, link, tags, priority, discount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_items)
    
    # Add admin user
    conn.execute(
        'INSERT OR IGNORE INTO users (user_id, first_name, username, credits, is_admin, referral_code) VALUES (?, ?, ?, ?, ?, ?)',
        (ADMIN_ONLY_ID, 'Admin', 'admin', 10000, 1, 'ADMIN2024')
    )
    
    conn.commit()
    logger.info("✅ Database initialized successfully")

# Initialize database on startup
init_db()

# Cache functions
def get_cached(key):
    if key in cache:
        data, timestamp = cache[key]
        if time.time() - timestamp < CACHE_TTL:
            return data
        else:
            del cache[key]
    return None

def set_cached(key, data):
    cache[key] = (data, time.time())

# Helper functions
def get_config():
    cached = get_cached('config')
    if cached:
        return cached
    
    conn = get_db()
    config_rows = conn.execute('SELECT key, value FROM config').fetchall()
    config = {row['key']: row['value'] for row in config_rows}
    
    set_cached('config', config)
    return config

def check_admin_auth(data):
    try:
        admin_id = int(data.get('admin_id', 0))
        admin_pass = data.get('admin_password', '')
        return admin_id == ADMIN_ONLY_ID and admin_pass == ADMIN_PASSWORD
    except:
        return False

def generate_referral_code(user_id):
    return f"REF{user_id}{hashlib.md5(str(user_id).encode()).hexdigest()[:6].upper()}"

# Fast routes with caching
@app.route('/')
@limiter.exempt
def index():
    tg_user_id = request.args.get('tg_user_id', '')
    ref = request.args.get('ref', '')
    return render_template('index.html', tg_user_id=tg_user_id, ref=ref)

@app.route('/api/user/<int:uid>')
@limiter.limit("30 per minute")
def get_user(uid):
    cache_key = f'user_{uid}'
    cached = get_cached(cache_key)
    if cached:
        return jsonify(cached)
    
    conn = get_db()
    
    # Get or create user
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (uid,)).fetchone()
    
    if not user:
        welcome_bonus = int(get_config().get('welcome_bonus', '100'))
        referral_code = generate_referral_code(uid)
        
        conn.execute(
            'INSERT INTO users (user_id, first_name, username, credits, referral_code) VALUES (?, ?, ?, ?, ?)',
            (uid, 'Telegram User', '', welcome_bonus, referral_code)
        )
        conn.commit()
        
        # Add welcome bonus to history
        date = datetime.now().strftime("%b %d, %Y")
        conn.execute(
            'INSERT INTO history (user_id, item_name, price, date, type) VALUES (?, ?, ?, ?, ?)',
            (uid, '🎁 Welcome Bonus', welcome_bonus, date, 'earn')
        )
        conn.commit()
        
        user = conn.execute('SELECT * FROM users WHERE user_id = ?', (uid,)).fetchone()
    
    # Daily reset check
    today = datetime.now().strftime("%Y-%m-%d")
    if user['last_ad_date'] != today:
        # Reset all ad counts
        conn.execute('''
            UPDATE users SET ads_today = 0, cnt_popup = 0, cnt_video = 0,
                           cnt_interstitial = 0, cnt_banner = 0, cnt_rewarded = 0, last_ad_date = ?
            WHERE user_id = ?
        ''', (today, uid))
        conn.commit()
        user = conn.execute('SELECT * FROM users WHERE user_id = ?', (uid,)).fetchone()
    
    user_dict = dict(user)
    user_dict['is_admin'] = bool(user['is_admin']) or (uid == ADMIN_ONLY_ID)
    user_dict['config'] = get_config()
    user_dict['ad_networks'] = AD_NETWORKS
    
    # Calculate daily progress
    daily_progress = {}
    for ad_type in AD_NETWORKS.keys():
        current = user[f'cnt_{ad_type}']
        limit = int(get_config().get(f'limit_{ad_type}', AD_NETWORKS[ad_type]['daily_limit']))
        daily_progress[ad_type] = {
            'current': current,
            'limit': limit,
            'percent': min((current / limit) * 100, 100) if limit > 0 else 0,
            'remaining': max(limit - current, 0)
        }
    
    user_dict['daily_progress'] = daily_progress
    
    set_cached(cache_key, user_dict)
    return jsonify(user_dict)

@app.route('/api/earn', methods=['POST'])
@limiter.limit("20 per minute")
def earn():
    data = request.json
    uid = data.get('uid')
    ad_type = data.get('ad_type')
    
    if not uid or not ad_type:
        return jsonify({'success': False, 'message': 'Missing data'}), 400
    
    if ad_type not in AD_NETWORKS:
        return jsonify({'success': False, 'message': 'Invalid ad type'}), 400
    
    conn = get_db()
    
    try:
        # Get user
        user = conn.execute('SELECT * FROM users WHERE user_id = ?', (uid,)).fetchone()
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Check cooldown
        if user['last_ad_time']:
            last_time = datetime.strptime(user['last_ad_time'], '%Y-%m-%d %H:%M:%S')
            current_time = datetime.now()
            time_diff = (current_time - last_time).seconds
            
            cooldown = int(get_config().get('ad_cooldown', '5'))
            if time_diff < cooldown:
                wait_time = cooldown - time_diff
                return jsonify({
                    'success': False,
                    'message': f'⏳ Please wait {wait_time} seconds',
                    'wait_time': wait_time
                })
        
        # Check daily limits
        config = get_config()
        daily_limit = int(config.get(f'limit_{ad_type}', AD_NETWORKS[ad_type]['daily_limit']))
        current_count = user[f'cnt_{ad_type}']
        
        if current_count >= daily_limit:
            return jsonify({
                'success': False,
                'message': f'Daily limit reached for {ad_type} ads'
            })
        
        # Check total daily ads
        max_daily = int(config.get('max_ads_daily', '250'))
        if user['ads_today'] >= max_daily:
            return jsonify({
                'success': False,
                'message': 'Maximum daily ads reached'
            })
        
        # Get reward amount
        reward = int(config.get(f'reward_{ad_type}', AD_NETWORKS[ad_type]['reward']))
        
        # Add bonus for consecutive ads
        if user['ads_today'] > 0 and user['ads_today'] % 10 == 0:
            reward += 2  # Bonus every 10 ads
            bonus_msg = " (+2 bonus!)"
        else:
            bonus_msg = ""
        
        # Process reward
        today = datetime.now().strftime("%Y-%m-%d")
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Update user
        conn.execute(f'''
            UPDATE users SET credits = credits + ?, total_earned = total_earned + ?,
                           ads_today = ads_today + 1, cnt_{ad_type} = cnt_{ad_type} + 1,
                           last_ad_time = ?, last_ad_date = ?
            WHERE user_id = ?
        ''', (reward, reward, current_time_str, today, uid))
        
        # Add to history
        date = datetime.now().strftime("%b %d, %Y")
        ad_name = ad_type.replace('_', ' ').title()
        conn.execute('''
            INSERT INTO history (user_id, item_name, price, date, type)
            VALUES (?, ?, ?, ?, ?)
        ''', (uid, f'📺 {ad_name} Ad', reward, date, 'earn'))
        
        conn.commit()
        
        # Clear cache
        cache_key = f'user_{uid}'
        if cache_key in cache:
            del cache[cache_key]
        
        # Get updated user
        updated_user = conn.execute('SELECT credits, ads_today FROM users WHERE user_id = ?', (uid,)).fetchone()
        
        return jsonify({
            'success': True,
            'reward': reward,
            'bonus_msg': bonus_msg,
            'credits': updated_user['credits'],
            'ads_today': updated_user['ads_today'],
            'daily_remaining': max_daily - updated_user['ads_today'],
            'message': f'🎉 +{reward} credits earned!{bonus_msg}'
        })
        
    except Exception as e:
        logger.error(f"Earn error: {e}")
        return jsonify({'success': False, 'message': 'Server error'}), 500
        
    finally:
        conn.close()

@app.route('/api/items')
@limiter.limit("30 per minute")
def get_items():
    cache_key = 'items_all'
    cached = get_cached(cache_key)
    if cached:
        return jsonify(cached)
    
    conn = get_db()
    items = conn.execute('''
        SELECT * FROM items 
        WHERE is_active = 1 
        ORDER BY priority DESC, price ASC
    ''').fetchall()
    
    items_list = [dict(item) for item in items]
    set_cached(cache_key, items_list)
    
    return jsonify(items_list)

@app.route('/api/items/category/<category>')
@limiter.limit("30 per minute")
def get_items_by_category(category):
    cache_key = f'items_{category}'
    cached = get_cached(cache_key)
    if cached:
        return jsonify(cached)
    
    conn = get_db()
    items = conn.execute('''
        SELECT * FROM items 
        WHERE category = ? AND is_active = 1 
        ORDER BY priority DESC, price ASC
    ''', (category,)).fetchall()
    
    items_list = [dict(item) for item in items]
    set_cached(cache_key, items_list)
    
    return jsonify(items_list)

@app.route('/api/buy', methods=['POST'])
@limiter.limit("20 per minute")
def buy():
    data = request.json
    uid = data.get('uid')
    item_id = data.get('item_id')
    
    if not uid or not item_id:
        return jsonify({'success': False, 'message': 'Missing data'}), 400
    
    conn = get_db()
    
    try:
        # Get user and item
        user = conn.execute('SELECT credits FROM users WHERE user_id = ?', (uid,)).fetchone()
        item = conn.execute('SELECT * FROM items WHERE id = ? AND is_active = 1', (item_id,)).fetchone()
        
        if not user or not item:
            return jsonify({'success': False, 'message': 'User or item not found'}), 404
        
        # Apply discount if any
        price = item['price']
        discount = item['discount'] or 0
        if discount > 0:
            price = price - (price * discount // 100)
        
        if user['credits'] < price:
            return jsonify({'success': False, 'message': 'Insufficient credits'})
        
        if item['stock'] <= 0:
            return jsonify({'success': False, 'message': 'Out of stock'})
        
        # Process purchase
        conn.execute('''
            UPDATE users SET credits = credits - ?, total_spent = total_spent + ?,
                           purchases = purchases + 1 WHERE user_id = ?
        ''', (price, price, uid))
        
        conn.execute('''
            UPDATE items SET sold = sold + 1, stock = stock - 1 WHERE id = ?
        ''', (item_id,))
        
        # Add to history
        date = datetime.now().strftime("%b %d, %Y")
        conn.execute('''
            INSERT INTO history (user_id, item_name, price, date, type,
                               item_content, item_ip, item_link, item_category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            uid, item['name'], price, date, 'spend',
            item['content'], item['ip'], item['link'], item['category']
        ))
        
        conn.commit()
        
        # Clear caches
        for key in list(cache.keys()):
            if key.startswith('items_') or key.startswith('user_'):
                del cache[key]
        
        return jsonify({
            'success': True,
            'message': '✅ Purchase successful!',
            'item': dict(item),
            'final_price': price,
            'discount_applied': discount
        })
        
    except Exception as e:
        logger.error(f"Buy error: {e}")
        return jsonify({'success': False, 'message': 'Purchase failed'}), 500
        
    finally:
        conn.close()

@app.route('/api/history/<int:uid>')
@limiter.limit("30 per minute")
def get_history(uid):
    cache_key = f'history_{uid}'
    cached = get_cached(cache_key)
    if cached:
        return jsonify(cached)
    
    conn = get_db()
    history = conn.execute(
        'SELECT * FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 50',
        (uid,)
    ).fetchall()
    
    history_list = [dict(row) for row in history]
    set_cached(cache_key, history_list, ttl=60)
    
    return jsonify(history_list)

# Fast admin routes with enhanced features
@app.route('/api/admin/quick_stats', methods=['POST'])
def admin_quick_stats():
    if not check_admin_auth(request.json):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    cache_key = 'admin_stats'
    cached = get_cached(cache_key)
    if cached:
        return jsonify(cached)
    
    conn = get_db()
    
    try:
        # Get stats quickly
        stats = {
            'total_users': conn.execute('SELECT COUNT(*) FROM users').fetchone()[0],
            'active_today': conn.execute("SELECT COUNT(*) FROM users WHERE last_ad_date = DATE('now')").fetchone()[0],
            'new_today': conn.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE('now')").fetchone()[0],
            'total_credits': conn.execute('SELECT SUM(credits) FROM users').fetchone()[0] or 0,
            'total_sales': conn.execute('SELECT SUM(price * sold) FROM items').fetchone()[0] or 0,
            'total_ads_today': conn.execute('SELECT SUM(ads_today) FROM users').fetchone()[0] or 0,
            'pending_withdrawals': 0,
            'server_time': datetime.now().isoformat()
        }
        
        result = {'success': True, 'stats': stats}
        set_cached(cache_key, result, ttl=10)  # 10 second cache for stats
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return jsonify({'success': False, 'message': 'Server error'}), 500

@app.route('/api/admin/full_control', methods=['POST'])
def admin_full_control():
    if not check_admin_auth(request.json):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    action = data.get('action')
    
    if action == 'get_users':
        limit = min(data.get('limit', 50), 100)
        offset = data.get('offset', 0)
        search = data.get('search', '')
        
        conn = get_db()
        query = 'SELECT * FROM users WHERE 1=1'
        params = []
        
        if search:
            if search.isdigit():
                query += ' AND user_id = ?'
                params.append(int(search))
            else:
                query += ' AND (first_name LIKE ? OR username LIKE ?)'
                params.extend([f'%{search}%', f'%{search}%'])
        
        query += ' ORDER BY user_id DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        users = conn.execute(query, params).fetchall()
        total = conn.execute('SELECT COUNT(*) FROM users WHERE 1=1' + 
                            (' AND user_id = ?' if search and search.isdigit() else 
                             ' AND (first_name LIKE ? OR username LIKE ?)' if search else ''),
                            params[:1] if search and search.isdigit() else 
                            params[:2] if search else []).fetchone()[0]
        
        return jsonify({
            'success': True,
            'users': [dict(user) for user in users],
            'total': total,
            'page': (offset // limit) + 1,
            'pages': (total + limit - 1) // limit
        })
    
    elif action == 'edit_user':
        user_id = data.get('user_id')
        field = data.get('field')
        value = data.get('value')
        
        if not all([user_id, field, value]):
            return jsonify({'success': False, 'message': 'Missing data'}), 400
        
        if field not in ['credits', 'total_earned', 'total_spent', 'is_admin']:
            return jsonify({'success': False, 'message': 'Invalid field'}), 400
        
        conn = get_db()
        conn.execute(f'UPDATE users SET {field} = ? WHERE user_id = ?', (value, user_id))
        conn.commit()
        
        # Clear cache
        cache_key = f'user_{user_id}'
        if cache_key in cache:
            del cache[cache_key]
        
        return jsonify({'success': True, 'message': f'Updated {field} for user {user_id}'})
    
    elif action == 'bulk_operation':
        operation = data.get('operation')
        user_ids = data.get('user_ids', [])
        value = data.get('value', 0)
        
        if not user_ids:
            return jsonify({'success': False, 'message': 'No users selected'}), 400
        
        conn = get_db()
        
        if operation == 'add_credits':
            placeholders = ','.join(['?'] * len(user_ids))
            conn.execute(f'UPDATE users SET credits = credits + ? WHERE user_id IN ({placeholders})',
                        [value] + user_ids)
            
            # Add to history for each user
            date = datetime.now().strftime("%b %d, %Y")
            for uid in user_ids:
                conn.execute(
                    'INSERT INTO history (user_id, item_name, price, date, type) VALUES (?, ?, ?, ?, ?)',
                    (uid, '💰 Admin Bulk Credit Add', value, date, 'earn')
                )
        
        elif operation == 'reset_ads':
            today = datetime.now().strftime("%Y-%m-%d")
            placeholders = ','.join(['?'] * len(user_ids))
            conn.execute(f'''
                UPDATE users SET ads_today = 0, cnt_popup = 0, cnt_video = 0,
                               cnt_interstitial = 0, cnt_banner = 0, cnt_rewarded = 0,
                               last_ad_date = ? WHERE user_id IN ({placeholders})
            ''', [today] + user_ids)
        
        elif operation == 'delete_users':
            if not data.get('confirm'):
                return jsonify({'success': False, 'message': 'Confirmation required'}), 400
            
            placeholders = ','.join(['?'] * len(user_ids))
            conn.execute(f'DELETE FROM users WHERE user_id IN ({placeholders})', user_ids)
            conn.execute(f'DELETE FROM history WHERE user_id IN ({placeholders})', user_ids)
        
        conn.commit()
        
        # Clear all user caches
        for uid in user_ids:
            cache_key = f'user_{uid}'
            if cache_key in cache:
                del cache[cache_key]
        
        return jsonify({'success': True, 'message': f'Operation completed for {len(user_ids)} users'})
    
    elif action == 'manage_items':
        sub_action = data.get('sub_action')
        
        if sub_action == 'get_all':
            conn = get_db()
            items = conn.execute('SELECT * FROM items ORDER BY id DESC').fetchall()
            return jsonify({
                'success': True,
                'items': [dict(item) for item in items]
            })
        
        elif sub_action == 'create':
            item_data = data.get('item', {})
            
            conn = get_db()
            conn.execute('''
                INSERT INTO items (name, category, price, stock, is_active, content, ip, link, tags, priority, discount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item_data.get('name'),
                item_data.get('category'),
                item_data.get('price'),
                item_data.get('stock', 999),
                item_data.get('is_active', 1),
                item_data.get('content'),
                item_data.get('ip', 'Global'),
                item_data.get('link', 'N/A'),
                item_data.get('tags', ''),
                item_data.get('priority', 0),
                item_data.get('discount', 0)
            ))
            conn.commit()
            
            # Clear items cache
            for key in list(cache.keys()):
                if key.startswith('items_'):
                    del cache[key]
            
            return jsonify({'success': True, 'message': 'Item created successfully'})
        
        elif sub_action == 'update':
            item_id = data.get('item_id')
            updates = data.get('updates', {})
            
            conn = get_db()
            set_clauses = []
            values = []
            
            for key, value in updates.items():
                set_clauses.append(f'{key} = ?')
                values.append(value)
            
            values.append(item_id)
            query = f'UPDATE items SET {", ".join(set_clauses)} WHERE id = ?'
            
            conn.execute(query, values)
            conn.commit()
            
            # Clear items cache
            for key in list(cache.keys()):
                if key.startswith('items_'):
                    del cache[key]
            
            return jsonify({'success': True, 'message': 'Item updated successfully'})
    
    elif action == 'system_config':
        sub_action = data.get('sub_action')
        
        if sub_action == 'get_all':
            config = get_config()
            return jsonify({'success': True, 'config': config})
        
        elif sub_action == 'update':
            updates = data.get('updates', {})
            
            conn = get_db()
            for key, value in updates.items():
                conn.execute(
                    'UPDATE config SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?',
                    (str(value), key)
                )
            
            conn.commit()
            
            # Clear config cache
            if 'config' in cache:
                del cache['config']
            
            return jsonify({'success': True, 'message': 'Configuration updated'})
    
    elif action == 'analytics':
        period = data.get('period', 'today')
        
        conn = get_db()
        
        if period == 'today':
            date_filter = "DATE(created_at) = DATE('now')"
        elif period == 'week':
            date_filter = "created_at >= DATE('now', '-7 days')"
        elif period == 'month':
            date_filter = "created_at >= DATE('now', '-30 days')"
        else:
            date_filter = "1=1"
        
        # User analytics
        user_stats = conn.execute(f'''
            SELECT 
                COUNT(*) as total_users,
                SUM(CASE WHEN {date_filter} THEN 1 ELSE 0 END) as new_users,
                AVG(credits) as avg_balance,
                MAX(credits) as max_balance
            FROM users
        ''').fetchone()
        
        # Ad analytics
        ad_stats = {}
        for ad_type in AD_NETWORKS.keys():
            total = conn.execute(f'SELECT SUM(cnt_{ad_type}) FROM users').fetchone()[0] or 0
            ad_stats[ad_type] = total
        
        # Revenue analytics
        revenue_stats = conn.execute(f'''
            SELECT 
                SUM(CASE WHEN type = 'earn' THEN price ELSE 0 END) as total_earned,
                SUM(CASE WHEN type = 'spend' THEN price ELSE 0 END) as total_spent,
                COUNT(*) as total_transactions
            FROM history
            WHERE {date_filter.replace('created_at', 'created_at')}
        ''').fetchone()
        
        return jsonify({
            'success': True,
            'analytics': {
                'period': period,
                'user_stats': dict(user_stats) if user_stats else {},
                'ad_stats': ad_stats,
                'revenue_stats': dict(revenue_stats) if revenue_stats else {},
                'timestamp': datetime.now().isoformat()
            }
        })
    
    elif action == 'export_data':
        export_type = data.get('type', 'json')
        
        conn = get_db()
        
        data_dict = {
            'export_time': datetime.now().isoformat(),
            'users': [dict(row) for row in conn.execute('SELECT * FROM users').fetchall()],
            'items': [dict(row) for row in conn.execute('SELECT * FROM items').fetchall()],
            'history': [dict(row) for row in conn.execute('SELECT * FROM history').fetchall()],
            'config': [dict(row) for row in conn.execute('SELECT * FROM config').fetchall()]
        }
        
        return jsonify({
            'success': True,
            'data': data_dict,
            'type': export_type
        })
    
    elif action == 'danger_zone':
        sub_action = data.get('sub_action')
        
        if not data.get('confirm'):
            return jsonify({'success': False, 'message': 'Confirmation required'}), 400
        
        conn = get_db()
        
        if sub_action == 'reset_all_credits':
            conn.execute('UPDATE users SET credits = 0')
            conn.commit()
            
            # Clear all user caches
            for key in list(cache.keys()):
                if key.startswith('user_'):
                    del cache[key]
            
            return jsonify({'success': True, 'message': 'All user credits reset to 0'})
        
        elif sub_action == 'clear_all_history':
            conn.execute('DELETE FROM history')
            conn.commit()
            
            # Clear history caches
            for key in list(cache.keys()):
                if key.startswith('history_'):
                    del cache[key]
            
            return jsonify({'success': True, 'message': 'All history cleared'})
        
        elif sub_action == 'reset_system':
            # This would restart the app in production
            # For now, just clear all caches
            cache.clear()
            return jsonify({'success': True, 'message': 'System cache cleared'})
    
    return jsonify({'success': False, 'message': 'Invalid action'}), 400

# System health and monitoring
@app.route('/health')
@limiter.exempt
def health():
    return jsonify({
        'status': 'healthy',
        'service': 'Own Bazar',
        'version': get_config().get('version', '3.0.0'),
        'timestamp': datetime.now().isoformat(),
        'uptime': int(time.time() - app_start_time),
        'cache_size': len(cache),
        'database': 'connected'
    })

@app.route('/ping')
@limiter.exempt
def ping():
    return jsonify({'pong': datetime.now().isoformat()})

@app.route('/status')
@limiter.exempt
def status():
    conn = get_db()
    
    stats = {
        'total_users': conn.execute('SELECT COUNT(*) FROM users').fetchone()[0],
        'total_items': conn.execute('SELECT COUNT(*) FROM items').fetchone()[0],
        'total_transactions': conn.execute('SELECT COUNT(*) FROM history').fetchone()[0],
        'active_users_today': conn.execute("SELECT COUNT(*) FROM users WHERE last_ad_date = DATE('now')").fetchone()[0],
        'system_time': datetime.now().isoformat(),
        'memory_usage': 'normal'
    }
    
    return jsonify(stats)

# Static files
@app.route('/static/<path:filename>')
@limiter.exempt
def static_files(filename):
    return send_file(f'static/{filename}')

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found', 'code': 404}), 404

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        'error': 'Rate limit exceeded',
        'message': 'Please try again later',
        'code': 429
    }), 429

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {e}")
    return jsonify({'error': 'Internal server error', 'code': 500}), 500

# App start time
app_start_time = time.time()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False,
        threaded=True
    )
