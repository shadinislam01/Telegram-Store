import sqlite3
import os
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import time
import logging
import random
from dotenv import load_dotenv
import sys
import importlib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
ADMIN_USER_ID = int(os.environ.get('ADMIN_ID', '6068468333'))
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
WEB_APP_URL = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')

app = Flask(__name__)
CORS(app)
app.secret_key = SECRET_KEY
DB_NAME = 'bot_database.db'

# Ad Networks Configuration
AD_NETWORKS = {
    'popup': {'reward': 4, 'daily_limit': 60},
    'video': {'reward': 6, 'daily_limit': 40},
    'interstitial': {'reward': 8, 'daily_limit': 30},
    'banner': {'reward': 3, 'daily_limit': 100}
}

# Database functions
def get_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    
    # Users table with ad counts for each network
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
        purchases INTEGER DEFAULT 0,
        last_ad_date TEXT,
        last_ad_time TEXT,
        is_admin INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
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
    
    # Config table
    conn.execute('''
    CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT,
        description TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Admins table for multiple admins
    conn.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE,
        username TEXT,
        permissions TEXT DEFAULT 'all',
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Insert default config for ad networks
    defaults = []
    for ad_type, config in AD_NETWORKS.items():
        defaults.append((f'reward_{ad_type}', str(config['reward']), f'Reward for {ad_type} ads'))
        defaults.append((f'limit_{ad_type}', str(config['daily_limit']), f'Daily limit for {ad_type} ads'))
    
    # Additional defaults
    defaults.extend([
        ('welcome_bonus', '100', 'Welcome bonus for new users'),
        ('referral_bonus', '15', 'Bonus for referrals'),
        ('ad_cooldown', '5', 'Cooldown between ads in seconds'),
        ('max_admins', '10', 'Maximum number of admins'),
        ('min_item_price', '10', 'Minimum item price'),
        ('max_item_price', '1000', 'Maximum item price'),
        ('daily_credit_limit', '1020', 'Maximum daily credits per user'),
        ('backup_enabled', 'true', 'Enable automatic backups')
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
             'USA', 'flyvpn.com', 'VPN,Premium'),
            
            ('Netflix Premium 4K', 'Streaming', 80, 8, 25, 1,
             'Email: netflix@account.com\nPassword: netflix123\nProfile: 4K Ultra HD',
             'USA', 'netflix.com', 'Streaming,Premium'),
            
            ('Spotify Premium', 'Music', 70, 10, 35, 1,
             'Username: spotify_user\nPassword: music2024\nFamily Plan: Yes',
             'Global', 'spotify.com', 'Music,Premium'),
            
            ('YouTube Premium', 'Streaming', 60, 15, 40, 1,
             'Email: youtube@premium.com\nPassword: youtube123\nNo Ads: Yes',
             'Global', 'youtube.com', 'Streaming,Music'),
            
            ('ChatGPT Plus', 'AI', 100, 5, 30, 1,
             'Email: chatgpt@openai.com\nPassword: ai12345\nGPT-4: Available',
             'Global', 'openai.com', 'AI,ChatGPT')
        ]
        
        conn.executemany('''
            INSERT INTO items (name, category, price, sold, stock, is_active, content, ip, link, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_items)
    
    # Add main admin user
    conn.execute(
        'INSERT OR IGNORE INTO users (user_id, first_name, username, credits, is_admin) VALUES (?, ?, ?, ?, ?)',
        (ADMIN_USER_ID, 'Admin', 'admin', 1000, 1)
    )
    
    # Add main admin to admins table
    conn.execute(
        'INSERT OR IGNORE INTO admins (user_id, username, permissions, created_by) VALUES (?, ?, ?, ?)',
        (ADMIN_USER_ID, 'admin', 'all', ADMIN_USER_ID)
    )
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized successfully")

# Initialize database on startup
init_db()

# Helper functions
def get_config():
    conn = get_db()
    config_rows = conn.execute('SELECT key, value FROM config').fetchall()
    conn.close()
    return {row['key']: row['value'] for row in config_rows}

def check_admin_auth(data):
    try:
        admin_id = int(data.get('admin_id', 0))
        admin_pass = data.get('admin_password', '')
        
        # Check if user exists and is admin
        conn = get_db()
        user = conn.execute('SELECT is_admin FROM users WHERE user_id = ?', (admin_id,)).fetchone()
        
        # Also check admins table
        admin_record = conn.execute('SELECT * FROM admins WHERE user_id = ?', (admin_id,)).fetchone()
        conn.close()
        
        # Check if user is admin and password matches
        if user and user['is_admin'] == 1 and admin_pass == ADMIN_PASSWORD:
            return True
            
        # Check admins table
        if admin_record and admin_pass == ADMIN_PASSWORD:
            return True
            
        # Also allow the main admin user
        if admin_id == ADMIN_USER_ID and admin_pass == ADMIN_PASSWORD:
            return True
            
        return False
    except:
        return False

def reset_all_ad_limits():
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    
    try:
        conn.execute('''
            UPDATE users SET ads_today = 0, cnt_popup = 0, cnt_video = 0,
                           cnt_interstitial = 0, cnt_banner = 0, last_ad_date = ?
        ''', (today,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Reset ad limits error: {e}")
        return False
    finally:
        conn.close()

# Routes
@app.route('/')
def index():
    tg_user_id = request.args.get('tg_user_id', '')
    ref = request.args.get('ref', '')
    return render_template('index.html', tg_user_id=tg_user_id, ref=ref)

@app.route('/api/user/<int:uid>')
def get_user(uid):
    conn = get_db()
    
    # Get or create user
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (uid,)).fetchone()
    
    if not user:
        welcome_bonus = int(get_config().get('welcome_bonus', '100'))
        conn.execute(
            'INSERT INTO users (user_id, first_name, username, credits) VALUES (?, ?, ?, ?)',
            (uid, 'Telegram User', '', welcome_bonus)
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
                           cnt_interstitial = 0, cnt_banner = 0, last_ad_date = ?
            WHERE user_id = ?
        ''', (today, uid))
        conn.commit()
        user = conn.execute('SELECT * FROM users WHERE user_id = ?', (uid,)).fetchone()
    
    user_dict = dict(user)
    user_dict['is_admin'] = bool(user['is_admin'] == 1)
    
    conn.close()
    return jsonify(user_dict)

@app.route('/api/earn', methods=['POST'])
def earn():
    data = request.json
    uid = data.get('uid')
    ad_type = data.get('ad_type')
    reward = data.get('reward')
    
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
        
        # Check daily limit
        config = get_config()
        daily_limit = int(config.get(f'limit_{ad_type}', AD_NETWORKS[ad_type]['daily_limit']))
        current_count = user[f'cnt_{ad_type}']
        
        if current_count >= daily_limit:
            return jsonify({
                'success': False,
                'message': f'Daily limit reached for {ad_type} ads'
            })
        
        # Get reward amount
        if not reward:
            reward = int(config.get(f'reward_{ad_type}', AD_NETWORKS[ad_type]['reward']))
        
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
        
        # Get updated user
        updated_user = conn.execute('SELECT credits, ads_today FROM users WHERE user_id = ?', (uid,)).fetchone()
        
        return jsonify({
            'success': True,
            'reward': reward,
            'credits': updated_user['credits'],
            'ads_today': updated_user['ads_today'],
            'message': f'🎉 +{reward} credits earned!'
        })
        
    except Exception as e:
        logger.error(f"Earn error: {e}")
        return jsonify({'success': False, 'message': 'Server error'}), 500
        
    finally:
        conn.close()

@app.route('/api/items')
def get_items():
    conn = get_db()
    items = conn.execute('SELECT * FROM items WHERE is_active = 1 ORDER BY category, price').fetchall()
    conn.close()
    return jsonify([dict(item) for item in items])

@app.route('/api/buy', methods=['POST'])
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
        
        if user['credits'] < item['price']:
            return jsonify({'success': False, 'message': 'Insufficient credits'})
        
        if item['stock'] <= 0:
            return jsonify({'success': False, 'message': 'Out of stock'})
        
        # Process purchase
        conn.execute('''
            UPDATE users SET credits = credits - ?, total_spent = total_spent + ?,
                           purchases = purchases + 1 WHERE user_id = ?
        ''', (item['price'], item['price'], uid))
        
        conn.execute('''
            UPDATE items SET sold = sold + 1, stock = stock - 1 WHERE id = ?
        ''', (item_id,))
        
        # Add to history with full item details
        date = datetime.now().strftime("%b %d, %Y")
        conn.execute('''
            INSERT INTO history (user_id, item_name, price, date, type,
                               item_content, item_ip, item_link, item_category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            uid, item['name'], item['price'], date, 'spend',
            item['content'], item['ip'], item['link'], item['category']
        ))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': '✅ Purchase successful!',
            'item': dict(item)
        })
        
    except Exception as e:
        logger.error(f"Buy error: {e}")
        return jsonify({'success': False, 'message': 'Purchase failed'}), 500
        
    finally:
        conn.close()

@app.route('/api/history/<int:uid>')
def get_history(uid):
    conn = get_db()
    history = conn.execute(
        'SELECT * FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 50',
        (uid,)
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in history])

@app.route('/api/purchases/<int:uid>')
def get_purchases(uid):
    conn = get_db()
    
    try:
        # Get only purchased items (type = 'spend')
        purchases = conn.execute(
            'SELECT * FROM history WHERE user_id = ? AND type = ? ORDER BY id DESC',
            (uid, 'spend')
        ).fetchall()
        
        return jsonify({
            'success': True,
            'items': [dict(row) for row in purchases]
        })
        
    except Exception as e:
        logger.error(f"Get purchases error: {e}")
        return jsonify({'success': False, 'message': 'Server error'}), 500
        
    finally:
        conn.close()

@app.route('/api/history/item/<int:history_id>')
def get_history_item(history_id):
    conn = get_db()
    
    try:
        # Get history item
        history = conn.execute(
            'SELECT * FROM history WHERE id = ?',
            (history_id,)
        ).fetchone()
        
        if not history:
            return jsonify({'success': False, 'message': 'Item not found'}), 404
        
        # Check if user owns this item (optional security)
        uid = request.args.get('user_id')
        if uid and int(uid) != history['user_id']:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        return jsonify({
            'success': True,
            'item': dict(history)
        })
        
    except Exception as e:
        logger.error(f"Get history item error: {e}")
        return jsonify({'success': False, 'message': 'Server error'}), 500
        
    finally:
        conn.close()

# ==================== ADMIN ROUTES ====================

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    admin_id = data.get('admin_id')
    admin_password = data.get('admin_password')
    
    if not admin_id or not admin_password:
        return jsonify({'success': False, 'message': 'Missing credentials'}), 400
    
    try:
        admin_id = int(admin_id)
        if check_admin_auth({'admin_id': admin_id, 'admin_password': admin_password}):
            # Get admin permissions
            conn = get_db()
            admin_record = conn.execute('SELECT permissions FROM admins WHERE user_id = ?', (admin_id,)).fetchone()
            conn.close()
            
            permissions = admin_record['permissions'] if admin_record else 'all'
            
            return jsonify({
                'success': True, 
                'message': 'Login successful',
                'permissions': permissions
            })
        else:
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
    except:
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@app.route('/api/admin/manage', methods=['POST'])
def admin_manage():
    data = request.json
    if not check_admin_auth(data):
        logger.error(f"Admin auth failed for user {data.get('admin_id')}")
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    action = data.get('action')
    conn = get_db()
    
    try:
        if action == 'add_credits':
            user_id = data.get('user_id')
            amount = data.get('amount', 0)
            
            if not user_id or not amount:
                return jsonify({'success': False, 'message': 'Missing user_id or amount'}), 400
            
            conn.execute('UPDATE users SET credits = credits + ? WHERE user_id = ?', (amount, user_id))
            
            # Add to history
            date = datetime.now().strftime("%b %d, %Y")
            conn.execute(
                'INSERT INTO history (user_id, item_name, price, date, type) VALUES (?, ?, ?, ?, ?)',
                (user_id, '💰 Admin Credit Add', amount, date, 'earn')
            )
            
            conn.commit()
            return jsonify({'success': True, 'message': f'Added {amount} credits to user {user_id}'})
        
        elif action == 'remove_credits':
            user_id = data.get('user_id')
            amount = data.get('amount', 0)
            
            if not user_id or not amount:
                return jsonify({'success': False, 'message': 'Missing user_id or amount'}), 400
            
            conn.execute('UPDATE users SET credits = credits - ? WHERE user_id = ?', (amount, user_id))
            
            # Add to history
            date = datetime.now().strftime("%b %d, %Y")
            conn.execute(
                'INSERT INTO history (user_id, item_name, price, date, type) VALUES (?, ?, ?, ?, ?)',
                (user_id, '⚠️ Admin Credit Remove', amount, date, 'spend')
            )
            
            conn.commit()
            return jsonify({'success': True, 'message': f'Removed {amount} credits from user {user_id}'})
        
        elif action == 'reset_user_ads':
            user_id = data.get('user_id')
            
            if not user_id:
                return jsonify({'success': False, 'message': 'Missing user_id'}), 400
            
            today = datetime.now().strftime("%Y-%m-%d")
            
            conn.execute('''
                UPDATE users SET ads_today = 0, cnt_popup = 0, cnt_video = 0,
                               cnt_interstitial = 0, cnt_banner = 0, last_ad_date = ?
                WHERE user_id = ?
            ''', (today, user_id))
            
            conn.commit()
            return jsonify({'success': True, 'message': f'Reset ads for user {user_id}'})
        
        elif action == 'reset_all_ads':
            today = datetime.now().strftime("%Y-%m-%d")
            
            conn.execute('''
                UPDATE users SET ads_today = 0, cnt_popup = 0, cnt_video = 0,
                               cnt_interstitial = 0, cnt_banner = 0, last_ad_date = ?
            ''', (today,))
            
            conn.commit()
            return jsonify({'success': True, 'message': 'Reset all user ad limits'})
        
        elif action == 'reset_all_credits':
            if not data.get('confirm'):
                return jsonify({'success': False, 'message': 'Confirmation required'}), 400
            
            conn.execute('UPDATE users SET credits = 0')
            conn.commit()
            return jsonify({'success': True, 'message': 'Reset all user credits to 0'})
        
        elif action == 'clear_all_history':
            if not data.get('confirm'):
                return jsonify({'success': False, 'message': 'Confirmation required'}), 400
            
            conn.execute('DELETE FROM history')
            conn.commit()
            return jsonify({'success': True, 'message': 'Cleared all history'})
        
        elif action == 'get_config':
            config = get_config()
            return jsonify({'success': True, 'config': config})
        
        elif action == 'update_config':
            updates = data.get('updates', {})
            
            if not updates:
                return jsonify({'success': False, 'message': 'No updates provided'}), 400
            
            for key, value in updates.items():
                conn.execute(
                    'UPDATE config SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?',
                    (str(value), key)
                )
            
            conn.commit()
            return jsonify({'success': True, 'message': 'Configuration updated'})
        
        elif action == 'get_users':
            limit = data.get('limit', 50)
            offset = data.get('offset', 0)
            
            users = conn.execute(
                'SELECT * FROM users ORDER BY user_id DESC LIMIT ? OFFSET ?',
                (limit, offset)
            ).fetchall()
            
            total = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            
            return jsonify({
                'success': True,
                'users': [dict(user) for user in users],
                'total': total
            })
        
        elif action == 'search_users':
            query = data.get('query', '')
            
            if not query:
                return jsonify({'success': False, 'message': 'Search query required'}), 400
            
            if query.isdigit():
                users = conn.execute(
                    'SELECT * FROM users WHERE user_id = ?',
                    (int(query),)
                ).fetchall()
            else:
                users = conn.execute(
                    'SELECT * FROM users WHERE first_name LIKE ? OR username LIKE ? ORDER BY user_id DESC LIMIT 50',
                    (f'%{query}%', f'%{query}%')
                ).fetchall()
            
            return jsonify({
                'success': True,
                'users': [dict(user) for user in users]
            })
        
        elif action == 'get_items_admin':
            items = conn.execute('SELECT * FROM items ORDER BY id DESC').fetchall()
            return jsonify({
                'success': True,
                'items': [dict(item) for item in items]
            })
        
        elif action == 'create_item':
            item_data = data.get('item', {})
            
            required_fields = ['name', 'category', 'price']
            for field in required_fields:
                if field not in item_data:
                    return jsonify({'success': False, 'message': f'Missing required field: {field}'}), 400
            
            conn.execute('''
                INSERT INTO items (name, category, price, stock, is_active, content, ip, link, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item_data.get('name'),
                item_data.get('category'),
                item_data.get('price'),
                item_data.get('stock', 999),
                item_data.get('is_active', 1),
                item_data.get('content', ''),
                item_data.get('ip', 'Global'),
                item_data.get('link', 'N/A'),
                item_data.get('tags', '')
            ))
            
            conn.commit()
            return jsonify({'success': True, 'message': 'Item created successfully'})
        
        elif action == 'update_item':
            item_id = data.get('item_id')
            updates = data.get('updates', {})
            
            if not item_id:
                return jsonify({'success': False, 'message': 'Item ID required'}), 400
            
            if not updates:
                return jsonify({'success': False, 'message': 'No updates provided'}), 400
            
            # Build update query
            set_clauses = []
            values = []
            
            for key, value in updates.items():
                set_clauses.append(f'{key} = ?')
                values.append(value)
            
            values.append(item_id)
            query = f'UPDATE items SET {", ".join(set_clauses)} WHERE id = ?'
            
            conn.execute(query, values)
            conn.commit()
            
            return jsonify({'success': True, 'message': 'Item updated successfully'})
        
        elif action == 'delete_item':
            item_id = data.get('item_id')
            
            if not item_id:
                return jsonify({'success': False, 'message': 'Item ID required'}), 400
            
            if not data.get('confirm'):
                return jsonify({'success': False, 'message': 'Confirmation required'}), 400
            
            conn.execute('DELETE FROM items WHERE id = ?', (item_id,))
            conn.commit()
            
            return jsonify({'success': True, 'message': 'Item deleted successfully'})
        
        elif action == 'get_stats':
            # User stats
            total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            active_today = conn.execute("SELECT COUNT(*) FROM users WHERE last_ad_date = DATE('now')").fetchone()[0]
            total_credits = conn.execute('SELECT SUM(credits) FROM users').fetchone()[0] or 0
            
            # Ad stats
            ad_stats = {}
            for ad_type in AD_NETWORKS.keys():
                total = conn.execute(f'SELECT SUM(cnt_{ad_type}) FROM users').fetchone()[0] or 0
                ad_stats[ad_type] = total
            
            # Item stats
            total_items = conn.execute('SELECT COUNT(*) FROM items').fetchone()[0]
            total_sales = conn.execute('SELECT SUM(price * sold) FROM items').fetchone()[0] or 0
            
            # Revenue stats
            total_earned = conn.execute('SELECT SUM(total_earned) FROM users').fetchone()[0] or 0
            total_spent = conn.execute('SELECT SUM(total_spent) FROM users').fetchone()[0] or 0
            
            return jsonify({
                'success': True,
                'stats': {
                    'total_users': total_users,
                    'active_today': active_today,
                    'total_credits': total_credits,
                    'ad_stats': ad_stats,
                    'total_items': total_items,
                    'total_sales': total_sales,
                    'total_earned': total_earned,
                    'total_spent': total_spent
                }
            })
        
        elif action == 'execute_sql':
            query = data.get('query', '')
            
            if not query:
                return jsonify({'success': False, 'message': 'Query required'}), 400
            
            # Security check - prevent dangerous queries
            dangerous_keywords = ['DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'UPDATE', 'INSERT']
            dangerous_query = any(keyword in query.upper() for keyword in dangerous_keywords)
            
            if dangerous_query:
                if not data.get('confirm'):
                    return jsonify({
                        'success': False, 
                        'message': 'Potentially dangerous query detected. Use with caution.',
                        'requires_confirm': True
                    }), 400
            
            try:
                # Execute query
                if query.strip().upper().startswith('SELECT'):
                    result = conn.execute(query).fetchall()
                    return jsonify({
                        'success': True,
                        'message': 'Query executed successfully',
                        'result': [dict(row) for row in result] if result else [],
                        'row_count': len(result)
                    })
                else:
                    # For non-SELECT queries
                    if not data.get('confirm_dangerous'):
                        return jsonify({
                            'success': False,
                            'message': 'Non-SELECT queries require additional confirmation',
                            'requires_dangerous_confirm': True
                        }), 400
                    
                    result = conn.execute(query)
                    conn.commit()
                    
                    return jsonify({
                        'success': True,
                        'message': f'Query executed. Rows affected: {result.rowcount}',
                        'row_count': result.rowcount
                    })
                    
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'SQL Error: {str(e)}'
                }), 400
        
        elif action == 'backup_database':
            # Get all data
            users = [dict(row) for row in conn.execute('SELECT * FROM users').fetchall()]
            items = [dict(row) for row in conn.execute('SELECT * FROM items').fetchall()]
            history = [dict(row) for row in conn.execute('SELECT * FROM history').fetchall()]
            config = [dict(row) for row in conn.execute('SELECT * FROM config').fetchall()]
            
            backup = {
                'timestamp': datetime.now().isoformat(),
                'users': users,
                'items': items,
                'history': history,
                'config': config
            }
            
            return jsonify({
                'success': True,
                'backup': backup,
                'message': 'Backup created successfully'
            })
        
        else:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
    except Exception as e:
        logger.error(f"Admin error: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
        
    finally:
        conn.close()

# ==================== NEW ADMIN ENDPOINTS ====================

@app.route('/api/admin/execute_sql', methods=['POST'])
def execute_sql():
    data = request.json
    if not check_admin_auth(data):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    query = data.get('query', '').strip()
    
    if not query:
        return jsonify({'success': False, 'message': 'SQL query required'}), 400
    
    # Security: Check for dangerous queries
    dangerous_keywords = ['DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'UPDATE', 'INSERT', 'CREATE', 'GRANT', 'REVOKE']
    query_upper = query.upper()
    
    if any(keyword in query_upper for keyword in dangerous_keywords):
        if not data.get('confirm_dangerous', False):
            return jsonify({
                'success': False, 
                'message': 'Potentially dangerous query. Add confirm_dangerous: true to execute.',
                'requires_confirm': True
            }), 400
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        
        if query_upper.startswith('SELECT'):
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description] if cursor.description else []
            
            result = []
            for row in rows:
                row_dict = {}
                for i, col in enumerate(columns):
                    row_dict[col] = row[i]
                result.append(row_dict)
            
            return jsonify({
                'success': True,
                'message': f'Query executed successfully. {len(result)} rows returned.',
                'result': result,
                'columns': columns,
                'row_count': len(result)
            })
        else:
            conn.commit()
            return jsonify({
                'success': True,
                'message': f'Query executed successfully. {cursor.rowcount} rows affected.',
                'row_count': cursor.rowcount
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'SQL Error: {str(e)}'
        }), 400
    finally:
        conn.close()

@app.route('/api/admin/backup', methods=['POST'])
def admin_backup():
    data = request.json
    if not check_admin_auth(data):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    conn = get_db()
    try:
        from datetime import datetime
        
        # Get all data
        tables = ['users', 'items', 'history', 'config', 'admins']
        backup_data = {
            'timestamp': datetime.now().isoformat(),
            'version': '2.0.0',
            'tables': {}
        }
        
        for table in tables:
            try:
                cursor = conn.cursor()
                cursor.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                columns = [description[0] for description in cursor.description]
                
                table_data = []
                for row in rows:
                    row_dict = {}
                    for i, col in enumerate(columns):
                        row_dict[col] = row[i]
                    table_data.append(row_dict)
                
                backup_data['tables'][table] = table_data
            except:
                continue  # Skip if table doesn't exist
        
        # Create backup file
        backup_filename = f"backup_ownbazar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        return jsonify({
            'success': True,
            'message': 'Backup created successfully',
            'backup': backup_data,
            'filename': backup_filename,
            'total_records': sum(len(backup_data['tables'].get(table, [])) for table in tables)
        })
        
    except Exception as e:
        logger.error(f"Backup error: {e}")
        return jsonify({'success': False, 'message': f'Backup failed: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/api/admin/system_config', methods=['POST'])
def system_config():
    data = request.json
    if not check_admin_auth(data):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    action = data.get('action')
    
    if action == 'get':
        config = get_config()
        system_info = {
            'database_size': os.path.getsize(DB_NAME) if os.path.exists(DB_NAME) else 0,
            'user_count': get_db().execute('SELECT COUNT(*) FROM users').fetchone()[0],
            'item_count': get_db().execute('SELECT COUNT(*) FROM items').fetchone()[0],
            'server_time': datetime.now().isoformat(),
            'version': '2.0.0',
            'python_version': sys.version,
            'platform': sys.platform
        }
        
        return jsonify({
            'success': True,
            'config': config,
            'system_info': system_info
        })
    
    elif action == 'update':
        updates = data.get('updates', {})
        
        if not updates:
            return jsonify({'success': False, 'message': 'No updates provided'}), 400
        
        conn = get_db()
        try:
            for key, value in updates.items():
                conn.execute(
                    'INSERT OR REPLACE INTO config (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)',
                    (key, str(value))
                )
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': 'Configuration updated successfully'
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'Update failed: {str(e)}'}), 500
        finally:
            conn.close()
    
    else:
        return jsonify({'success': False, 'message': 'Invalid action'}), 400

@app.route('/api/admin/ad_statistics', methods=['POST'])
def ad_statistics():
    data = request.json
    if not check_admin_auth(data):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    period = data.get('period', 'today')  # today, week, month, all
    
    conn = get_db()
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Get total ad views by type
        ad_stats = {}
        total_revenue = 0
        
        for ad_type in ['popup', 'video', 'interstitial', 'banner']:
            total_views = conn.execute(f'SELECT SUM(cnt_{ad_type}) FROM users').fetchone()[0] or 0
            today_views = conn.execute(f'''
                SELECT SUM(cnt_{ad_type}) FROM users WHERE last_ad_date = ?
            ''', (today,)).fetchone()[0] or 0
            
            # Get reward from config
            reward = int(get_config().get(f'reward_{ad_type}', AD_NETWORKS[ad_type]['reward']))
            
            ad_stats[ad_type] = {
                'total_views': total_views,
                'today_views': today_views,
                'reward': reward,
                'total_earned': total_views * reward,
                'today_earned': today_views * reward
            }
            
            total_revenue += total_views * reward
        
        # Get user engagement
        active_users = conn.execute(
            'SELECT COUNT(*) FROM users WHERE last_ad_date = ?', 
            (today,)
        ).fetchone()[0]
        
        total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        
        # Get top earners
        top_earners = conn.execute('''
            SELECT user_id, first_name, username, total_earned 
            FROM users 
            ORDER BY total_earned DESC 
            LIMIT 10
        ''').fetchall()
        
        # Get hourly stats for today (simplified)
        hour_stats = []
        current_hour = datetime.now().hour
        for hour in range(24):
            # Simulate some data - in production you'd track actual timestamps
            if hour <= current_hour:
                views = random.randint(10, 100)
            else:
                views = 0
            hour_stats.append({
                'hour': hour,
                'views': views,
                'revenue': views * 5  # Average reward
            })
        
        return jsonify({
            'success': True,
            'period': period,
            'ad_stats': ad_stats,
            'user_engagement': {
                'active_today': active_users,
                'total_users': total_users,
                'engagement_rate': (active_users / total_users * 100) if total_users > 0 else 0
            },
            'revenue': {
                'total': total_revenue,
                'today': sum(ad_stats[ad_type]['today_earned'] for ad_type in ad_stats),
                'estimated_monthly': total_revenue * 30
            },
            'top_earners': [dict(user) for user in top_earners],
            'hourly_stats': hour_stats,
            'summary': {
                'total_ad_views': sum(ad_stats[ad_type]['total_views'] for ad_type in ad_stats),
                'today_ad_views': sum(ad_stats[ad_type]['today_views'] for ad_type in ad_stats),
                'avg_revenue_per_user': total_revenue / total_users if total_users > 0 else 0
            }
        })
        
    except Exception as e:
        logger.error(f"Ad statistics error: {e}")
        return jsonify({'success': False, 'message': f'Failed to get statistics: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/api/admin/bulk_operations', methods=['POST'])
def bulk_operations():
    data = request.json
    if not check_admin_auth(data):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    operation = data.get('operation')
    
    if operation == 'add_credits':
        amount = data.get('amount')
        user_ids = data.get('user_ids', [])
        
        if not amount:
            return jsonify({'success': False, 'message': 'Amount required'}), 400
        
        conn = get_db()
        try:
            if user_ids and len(user_ids) > 0:
                # Add to specific users
                placeholders = ','.join(['?'] * len(user_ids))
                conn.execute(f'''
                    UPDATE users SET credits = credits + ? 
                    WHERE user_id IN ({placeholders})
                ''', [amount] + user_ids)
                
                # Add to history
                date = datetime.now().strftime("%b %d, %Y")
                for user_id in user_ids:
                    conn.execute('''
                        INSERT INTO history (user_id, item_name, price, date, type)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (user_id, f'💰 Bulk Credit Add', amount, date, 'earn'))
                
                affected = len(user_ids)
            else:
                # Add to all users
                users = conn.execute('SELECT user_id FROM users').fetchall()
                user_ids = [user['user_id'] for user in users]
                
                conn.execute('UPDATE users SET credits = credits + ?', (amount,))
                
                # Add to history
                date = datetime.now().strftime("%b %d, %Y")
                for user_id in user_ids:
                    conn.execute('''
                        INSERT INTO history (user_id, item_name, price, date, type)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (user_id, f'💰 Bulk Credit Add', amount, date, 'earn'))
                
                affected = len(user_ids)
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': f'Added {amount} credits to {affected} users'
            })
            
        except Exception as e:
            return jsonify({'success': False, 'message': f'Operation failed: {str(e)}'}), 500
        finally:
            conn.close()
    
    elif operation == 'reset_all_limits':
        try:
            reset_all_ad_limits()
            return jsonify({'success': True, 'message': 'All ad limits reset successfully'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Reset failed: {str(e)}'}), 500
    
    elif operation == 'mass_message':
        message = data.get('message')
        user_ids = data.get('user_ids', [])
        
        if not message:
            return jsonify({'success': False, 'message': 'Message required'}), 400
        
        # In production, implement actual messaging
        return jsonify({
            'success': True,
            'message': f'Message prepared for {len(user_ids) if user_ids else "all"} users'
        })
    
    else:
        return jsonify({'success': False, 'message': 'Invalid operation'}), 400

@app.route('/api/admin/search', methods=['POST'])
def admin_search():
    data = request.json
    if not check_admin_auth(data):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    search_type = data.get('type', 'users')
    query = data.get('query', '').strip()
    
    if not query and search_type != 'all':
        return jsonify({'success': False, 'message': 'Search query required'}), 400
    
    conn = get_db()
    try:
        if search_type == 'users':
            # Search by user_id, username, or first_name
            if query.isdigit():
                users = conn.execute('''
                    SELECT * FROM users 
                    WHERE user_id = ? 
                    ORDER BY user_id DESC
                ''', (int(query),)).fetchall()
            else:
                users = conn.execute('''
                    SELECT * FROM users 
                    WHERE username LIKE ? OR first_name LIKE ? 
                    ORDER BY user_id DESC
                ''', (f'%{query}%', f'%{query}%')).fetchall()
            
            return jsonify({
                'success': True,
                'type': 'users',
                'results': [dict(user) for user in users],
                'count': len(users)
            })
        
        elif search_type == 'items':
            items = conn.execute('''
                SELECT * FROM items 
                WHERE name LIKE ? OR category LIKE ? OR tags LIKE ?
                ORDER BY id DESC
            ''', (f'%{query}%', f'%{query}%', f'%{query}%')).fetchall()
            
            return jsonify({
                'success': True,
                'type': 'items',
                'results': [dict(item) for item in items],
                'count': len(items)
            })
        
        elif search_type == 'history':
            history = conn.execute('''
                SELECT h.*, u.first_name, u.username 
                FROM history h
                LEFT JOIN users u ON h.user_id = u.user_id
                WHERE h.item_name LIKE ? OR u.username LIKE ? OR u.first_name LIKE ?
                ORDER BY h.id DESC
                LIMIT 100
            ''', (f'%{query}%', f'%{query}%', f'%{query}%')).fetchall()
            
            return jsonify({
                'success': True,
                'type': 'history',
                'results': [dict(row) for row in history],
                'count': len(history)
            })
        
        elif search_type == 'all':
            # Search across all tables
            users = conn.execute('''
                SELECT * FROM users 
                WHERE username LIKE ? OR first_name LIKE ? 
                ORDER BY user_id DESC LIMIT 20
            ''', (f'%{query}%', f'%{query}%')).fetchall()
            
            items = conn.execute('''
                SELECT * FROM items 
                WHERE name LIKE ? OR category LIKE ? 
                ORDER BY id DESC LIMIT 20
            ''', (f'%{query}%', f'%{query}%')).fetchall()
            
            history = conn.execute('''
                SELECT h.*, u.first_name, u.username 
                FROM history h
                LEFT JOIN users u ON h.user_id = u.user_id
                WHERE h.item_name LIKE ? 
                ORDER BY h.id DESC LIMIT 20
            ''', (f'%{query}%',)).fetchall()
            
            return jsonify({
                'success': True,
                'type': 'all',
                'users': [dict(user) for user in users],
                'items': [dict(item) for item in items],
                'history': [dict(row) for row in history],
                'counts': {
                    'users': len(users),
                    'items': len(items),
                    'history': len(history)
                }
            })
        
        else:
            return jsonify({'success': False, 'message': 'Invalid search type'}), 400
            
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({'success': False, 'message': f'Search failed: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/api/admin/items', methods=['POST'])
def admin_items():
    data = request.json
    if not check_admin_auth(data):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    action = data.get('action')
    
    if action == 'list':
        conn = get_db()
        try:
            items = conn.execute('SELECT * FROM items ORDER BY id DESC').fetchall()
            
            return jsonify({
                'success': True,
                'items': [dict(item) for item in items],
                'count': len(items)
            })
        finally:
            conn.close()
    
    elif action == 'create':
        item_data = data.get('item', {})
        
        required_fields = ['name', 'category', 'price']
        for field in required_fields:
            if field not in item_data:
                return jsonify({'success': False, 'message': f'Missing required field: {field}'}), 400
        
        conn = get_db()
        try:
            conn.execute('''
                INSERT INTO items (name, category, price, stock, content, ip, link, tags, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item_data['name'],
                item_data['category'],
                item_data['price'],
                item_data.get('stock', 999),
                item_data.get('content', 'Account details will be provided after purchase.'),
                item_data.get('ip', 'Global'),
                item_data.get('link', 'N/A'),
                item_data.get('tags', item_data['category']),
                item_data.get('is_active', 1)
            ))
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': 'Item created successfully',
                'item_id': conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'Create failed: {str(e)}'}), 500
        finally:
            conn.close()
    
    elif action == 'update':
        item_id = data.get('item_id')
        updates = data.get('updates', {})
        
        if not item_id:
            return jsonify({'success': False, 'message': 'Item ID required'}), 400
        
        conn = get_db()
        try:
            # Build dynamic update query
            set_fields = []
            values = []
            
            for field, value in updates.items():
                set_fields.append(f"{field} = ?")
                values.append(value)
            
            if not set_fields:
                return jsonify({'success': False, 'message': 'No updates provided'}), 400
            
            values.append(item_id)
            query = f"UPDATE items SET {', '.join(set_fields)} WHERE id = ?"
            
            conn.execute(query, values)
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': 'Item updated successfully'
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'Update failed: {str(e)}'}), 500
        finally:
            conn.close()
    
    elif action == 'delete':
        item_id = data.get('item_id')
        
        if not item_id:
            return jsonify({'success': False, 'message': 'Item ID required'}), 400
        
        if not data.get('confirm', False):
            return jsonify({
                'success': False,
                'message': 'Confirmation required',
                'requires_confirm': True
            }), 400
        
        conn = get_db()
        try:
            conn.execute('DELETE FROM items WHERE id = ?', (item_id,))
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': 'Item deleted successfully'
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'Delete failed: {str(e)}'}), 500
        finally:
            conn.close()
    
    elif action == 'batch_update':
        items = data.get('items', [])
        
        if not items:
            return jsonify({'success': False, 'message': 'No items provided'}), 400
        
        conn = get_db()
        try:
            for item in items:
                if 'id' in item and 'updates' in item:
                    set_fields = []
                    values = []
                    
                    for field, value in item['updates'].items():
                        set_fields.append(f"{field} = ?")
                        values.append(value)
                    
                    values.append(item['id'])
                    query = f"UPDATE items SET {', '.join(set_fields)} WHERE id = ?"
                    conn.execute(query, values)
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': f'Updated {len(items)} items successfully'
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'Batch update failed: {str(e)}'}), 500
        finally:
            conn.close()
    
    else:
        return jsonify({'success': False, 'message': 'Invalid action'}), 400

@app.route('/api/admin/stock', methods=['POST'])
def stock_management():
    data = request.json
    if not check_admin_auth(data):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    action = data.get('action')
    
    if action == 'update':
        item_id = data.get('item_id')
        stock = data.get('stock')
        
        if not item_id or stock is None:
            return jsonify({'success': False, 'message': 'Item ID and stock required'}), 400
        
        conn = get_db()
        try:
            conn.execute('UPDATE items SET stock = ? WHERE id = ?', (stock, item_id))
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': f'Stock updated to {stock}'
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'Update failed: {str(e)}'}), 500
        finally:
            conn.close()
    
    elif action == 'low_stock':
        threshold = data.get('threshold', 10)
        
        conn = get_db()
        try:
            items = conn.execute('''
                SELECT * FROM items 
                WHERE stock <= ? AND is_active = 1
                ORDER BY stock ASC
            ''', (threshold,)).fetchall()
            
            return jsonify({
                'success': True,
                'items': [dict(item) for item in items],
                'count': len(items),
                'threshold': threshold
            })
        finally:
            conn.close()
    
    elif action == 'restock':
        item_id = data.get('item_id')
        quantity = data.get('quantity', 10)
        
        if not item_id:
            return jsonify({'success': False, 'message': 'Item ID required'}), 400
        
        conn = get_db()
        try:
            conn.execute('UPDATE items SET stock = stock + ? WHERE id = ?', (quantity, item_id))
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': f'Restocked {quantity} units'
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'Restock failed: {str(e)}'}), 500
        finally:
            conn.close()
    
    else:
        return jsonify({'success': False, 'message': 'Invalid action'}), 400

@app.route('/api/admin/system', methods=['POST'])
def system_management():
    data = request.json
    if not check_admin_auth(data):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    action = data.get('action')
    
    if action == 'restart':
        # In production, you might want to implement actual restart logic
        # For now, we'll just clear some caches
        try:
            # Reload modules
            importlib.reload(sys.modules[__name__])
            
            return jsonify({
                'success': True,
                'message': 'System restart initiated (simulated)'
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'Restart failed: {str(e)}'}), 500
    
    elif action == 'clear_cache':
        # Clear database caches
        conn = get_db()
        try:
            # Optimize database
            conn.execute('VACUUM')
            conn.execute('PRAGMA optimize')
            
            return jsonify({
                'success': True,
                'message': 'Cache cleared and database optimized'
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'Clear cache failed: {str(e)}'}), 500
        finally:
            conn.close()
    
    elif action == 'stats':
        conn = get_db()
        try:
            stats = {
                'users': conn.execute('SELECT COUNT(*) FROM users').fetchone()[0],
                'active_users': conn.execute("SELECT COUNT(*) FROM users WHERE last_ad_date = DATE('now')").fetchone()[0],
                'items': conn.execute('SELECT COUNT(*) FROM items').fetchone()[0],
                'active_items': conn.execute('SELECT COUNT(*) FROM items WHERE is_active = 1').fetchone()[0],
                'history': conn.execute('SELECT COUNT(*) FROM history').fetchone()[0],
                'total_credits': conn.execute('SELECT SUM(credits) FROM users').fetchone()[0] or 0,
                'total_earned': conn.execute('SELECT SUM(total_earned) FROM users').fetchone()[0] or 0,
                'total_spent': conn.execute('SELECT SUM(total_spent) FROM users').fetchone()[0] or 0,
                'database_size': os.path.getsize(DB_NAME) if os.path.exists(DB_NAME) else 0,
                'admins': conn.execute('SELECT COUNT(*) FROM admins').fetchone()[0]
            }
            
            return jsonify({
                'success': True,
                'stats': stats
            })
        finally:
            conn.close()
    
    elif action == 'health':
        # System health check
        health_status = {
            'database': 'healthy' if os.path.exists(DB_NAME) else 'unhealthy',
            'disk_space': os.statvfs('/').f_bavail * os.statvfs('/').f_frsize if hasattr(os, 'statvfs') else 'unknown',
            'memory': 'unknown',
            'uptime': time.time(),
            'timestamp': datetime.now().isoformat()
        }
        
        return jsonify({
            'success': True,
            'health': health_status
        })
    
    else:
        return jsonify({'success': False, 'message': 'Invalid action'}), 400

@app.route('/api/admin/admins', methods=['POST'])
def admin_management():
    data = request.json
    if not check_admin_auth(data):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    action = data.get('action')
    
    if action == 'list':
        conn = get_db()
        try:
            admins = conn.execute('''
                SELECT a.*, u.username, u.first_name 
                FROM admins a
                LEFT JOIN users u ON a.user_id = u.user_id
                ORDER BY a.id DESC
            ''').fetchall()
            
            return jsonify({
                'success': True,
                'admins': [dict(admin) for admin in admins],
                'count': len(admins)
            })
        finally:
            conn.close()
    
    elif action == 'add':
        user_id = data.get('user_id')
        permissions = data.get('permissions', 'readonly')
        
        if not user_id:
            return jsonify({'success': False, 'message': 'User ID required'}), 400
        
        # Check max admins limit
        config = get_config()
        max_admins = int(config.get('max_admins', '10'))
        
        conn = get_db()
        try:
            current_count = conn.execute('SELECT COUNT(*) FROM admins').fetchone()[0]
            if current_count >= max_admins:
                return jsonify({
                    'success': False,
                    'message': f'Maximum admin limit reached ({max_admins})'
                }), 400
            
            # Check if user exists
            user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
            if not user:
                return jsonify({'success': False, 'message': 'User not found'}), 404
            
            # Check if already admin
            existing = conn.execute('SELECT * FROM admins WHERE user_id = ?', (user_id,)).fetchone()
            if existing:
                return jsonify({'success': False, 'message': 'User is already an admin'}), 400
            
            # Add to admins table
            conn.execute('''
                INSERT INTO admins (user_id, username, permissions, created_by)
                VALUES (?, ?, ?, ?)
            ''', (user_id, user['username'], permissions, data.get('admin_id')))
            
            # Also update users table
            conn.execute('UPDATE users SET is_admin = 1 WHERE user_id = ?', (user_id,))
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': f'User {user_id} added as admin with {permissions} permissions'
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'Add admin failed: {str(e)}'}), 500
        finally:
            conn.close()
    
    elif action == 'remove':
        admin_id = data.get('admin_id_to_remove')
        
        if not admin_id:
            return jsonify({'success': False, 'message': 'Admin ID to remove required'}), 400
        
        # Prevent removing main admin
        if int(admin_id) == ADMIN_USER_ID:
            return jsonify({'success': False, 'message': 'Cannot remove main admin'}), 400
        
        conn = get_db()
        try:
            # Remove from admins table
            conn.execute('DELETE FROM admins WHERE user_id = ?', (admin_id,))
            
            # Update users table
            conn.execute('UPDATE users SET is_admin = 0 WHERE user_id = ?', (admin_id,))
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': f'Admin {admin_id} removed successfully'
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'Remove admin failed: {str(e)}'}), 500
        finally:
            conn.close()
    
    elif action == 'update_permissions':
        admin_id = data.get('admin_id')
        permissions = data.get('permissions')
        
        if not admin_id or not permissions:
            return jsonify({'success': False, 'message': 'Admin ID and permissions required'}), 400
        
        conn = get_db()
        try:
            conn.execute('UPDATE admins SET permissions = ? WHERE user_id = ?', (permissions, admin_id))
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': f'Permissions updated for admin {admin_id}'
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'Update permissions failed: {str(e)}'}), 500
        finally:
            conn.close()
    
    else:
        return jsonify({'success': False, 'message': 'Invalid action'}), 400

@app.route('/api/admin/dashboard', methods=['POST'])
def admin_dashboard():
    data = request.json
    if not check_admin_auth(data):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    conn = get_db()
    
    try:
        # Recent activity
        recent_activity = conn.execute('''
            SELECT h.*, u.first_name, u.username FROM history h
            LEFT JOIN users u ON h.user_id = u.user_id
            ORDER BY h.id DESC LIMIT 20
        ''').fetchall()
        
        # Top earners
        top_earners = conn.execute('''
            SELECT user_id, first_name, username, credits, total_earned 
            FROM users 
            ORDER BY total_earned DESC 
            LIMIT 10
        ''').fetchall()
        
        # Popular items
        popular_items = conn.execute('''
            SELECT name, category, price, sold, stock 
            FROM items 
            WHERE is_active = 1 
            ORDER BY sold DESC 
            LIMIT 10
        ''').fetchall()
        
        # System stats
        stats = {
            'users': conn.execute('SELECT COUNT(*) FROM users').fetchone()[0],
            'active_today': conn.execute("SELECT COUNT(*) FROM users WHERE last_ad_date = DATE('now')").fetchone()[0],
            'items': conn.execute('SELECT COUNT(*) FROM items').fetchone()[0],
            'total_credits': conn.execute('SELECT SUM(credits) FROM users').fetchone()[0] or 0,
            'revenue_today': 0,  # Calculate from history
            'new_users_today': conn.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE('now')").fetchone()[0]
        }
        
        return jsonify({
            'success': True,
            'recent_activity': [dict(row) for row in recent_activity],
            'top_earners': [dict(row) for row in top_earners],
            'popular_items': [dict(row) for row in popular_items],
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return jsonify({'success': False, 'message': 'Server error'}), 500
        
    finally:
        conn.close()

@app.route('/api/admin/make_admin', methods=['POST'])
def make_admin():
    data = request.json
    if not check_admin_auth(data):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    target_user_id = data.get('user_id')
    
    if not target_user_id:
        return jsonify({'success': False, 'message': 'User ID required'}), 400
    
    conn = get_db()
    
    try:
        # Check if user exists
        user = conn.execute('SELECT * FROM users WHERE user_id = ?', (target_user_id,)).fetchone()
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Make user admin
        conn.execute('UPDATE users SET is_admin = 1 WHERE user_id = ?', (target_user_id,))
        
        # Add to admins table
        conn.execute('''
            INSERT OR REPLACE INTO admins (user_id, username, permissions, created_by)
            VALUES (?, ?, ?, ?)
        ''', (target_user_id, user['username'], 'all', data.get('admin_id')))
        
        conn.commit()
        
        return jsonify({'success': True, 'message': f'User {target_user_id} is now admin'})
        
    except Exception as e:
        logger.error(f"Make admin error: {e}")
        return jsonify({'success': False, 'message': 'Server error'}), 500
        
    finally:
        conn.close()

# System routes
@app.route('/health')
def health():
    conn = get_db()
    try:
        # Test database connection
        conn.execute('SELECT 1').fetchone()
        db_status = 'connected'
    except:
        db_status = 'disconnected'
    finally:
        conn.close()
    
    return jsonify({
        'status': 'ok',
        'service': 'Own Bazar',
        'timestamp': datetime.now().isoformat(),
        'database': db_status,
        'version': '2.0.0'
    })

@app.route('/ping')
def ping():
    return jsonify({'pong': datetime.now().isoformat()})

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found', 'code': 404}), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {e}")
    return jsonify({'error': 'Internal server error', 'code': 500}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
