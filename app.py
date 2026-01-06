import sqlite3
import os
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import time
import logging
from dotenv import load_dotenv

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

# Ad Networks Configuration - Now dynamic from database
AD_NETWORKS = {}

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
    
    # Ad networks table
    conn.execute('''
    CREATE TABLE IF NOT EXISTS ad_networks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad_key TEXT UNIQUE,
        name TEXT,
        type TEXT,
        script_url TEXT,
        zone_id TEXT,
        reward INTEGER DEFAULT 4,
        daily_limit INTEGER,
        description TEXT,
        active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Ad views per user table
    conn.execute('''
    CREATE TABLE IF NOT EXISTS user_ad_views (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        ad_key TEXT,
        views_today INTEGER DEFAULT 0,
        last_view_date TEXT,
        total_views INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    ''')
    
    # Insert default config
    defaults = [
        ('welcome_bonus', '100', 'Welcome bonus for new users'),
        ('referral_bonus', '15', 'Bonus for referrals'),
        ('ad_cooldown', '5', 'Cooldown between ads in seconds')
    ]
    
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
    
    # Add admin user
    conn.execute(
        'INSERT OR IGNORE INTO users (user_id, first_name, username, credits, is_admin) VALUES (?, ?, ?, ?, ?)',
        (ADMIN_USER_ID, 'Admin', 'admin', 1000, 1)
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
        conn.close()
        
        # Check if user is admin and password matches
        if user and user['is_admin'] == 1 and admin_pass == ADMIN_PASSWORD:
            return True
            
        # Also allow the main admin user
        if admin_id == ADMIN_USER_ID and admin_pass == ADMIN_PASSWORD:
            return True
            
        return False
    except:
        return False

def load_ad_networks():
    """Load ad networks from database"""
    conn = get_db()
    networks = {}
    
    try:
        rows = conn.execute('SELECT * FROM ad_networks WHERE active = 1').fetchall()
        for row in rows:
            networks[row['ad_key']] = {
                'name': row['name'],
                'type': row['type'],
                'script_url': row['script_url'],
                'zone_id': row['zone_id'],
                'reward': row['reward'],
                'daily_limit': row['daily_limit'],
                'description': row['description'],
                'active': bool(row['active'])
            }
    except Exception as e:
        logger.error(f"Error loading ad networks: {e}")
    
    conn.close()
    return networks

def update_ad_networks_global():
    """Update the global AD_NETWORKS variable"""
    global AD_NETWORKS
    AD_NETWORKS = load_ad_networks()
    logger.info(f"Loaded {len(AD_NETWORKS)} ad networks")

# Initial load
update_ad_networks_global()

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
            UPDATE users SET ads_today = 0, last_ad_date = ?
            WHERE user_id = ?
        ''', (today, uid))
        
        # Reset user_ad_views for today
        conn.execute('''
            UPDATE user_ad_views SET views_today = 0, last_view_date = ?
            WHERE user_id = ? AND last_view_date != ?
        ''', (today, uid, today))
        
        conn.commit()
        user = conn.execute('SELECT * FROM users WHERE user_id = ?', (uid,)).fetchone()
    
    # Get ad views for today
    ad_views = {}
    for ad_key in AD_NETWORKS.keys():
        view_data = conn.execute('''
            SELECT views_today FROM user_ad_views 
            WHERE user_id = ? AND ad_key = ? AND last_view_date = ?
        ''', (uid, ad_key, today)).fetchone()
        
        if view_data:
            ad_views[ad_key] = view_data['views_today']
        else:
            ad_views[ad_key] = 0
    
    user_dict = dict(user)
    user_dict['is_admin'] = bool(user['is_admin'] == 1)
    user_dict['ad_views'] = ad_views
    
    conn.close()
    return jsonify(user_dict)

@app.route('/api/earn', methods=['POST'])
def earn():
    data = request.json
    uid = data.get('uid')
    ad_key = data.get('ad_key')
    reward = data.get('reward')
    
    if not uid or not ad_key:
        return jsonify({'success': False, 'message': 'Missing data'}), 400
    
    # Check if ad network exists and is active
    ad_config = AD_NETWORKS.get(ad_key)
    if not ad_config or not ad_config['active']:
        return jsonify({'success': False, 'message': 'Ad network not available'}), 400
    
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
        
        # Check daily limit for this ad network
        today = datetime.now().strftime("%Y-%m-%d")
        daily_limit = ad_config.get('daily_limit')
        
        if daily_limit:
            # Get today's views for this ad
            view_data = conn.execute('''
                SELECT views_today FROM user_ad_views 
                WHERE user_id = ? AND ad_key = ? AND last_view_date = ?
            ''', (uid, ad_key, today)).fetchone()
            
            current_views = view_data['views_today'] if view_data else 0
            
            if current_views >= daily_limit:
                return jsonify({
                    'success': False,
                    'message': f'Daily limit reached for this ad'
                })
        
        # Get reward amount
        if not reward:
            reward = ad_config.get('reward', 4)
        
        # Process reward
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Update user
        conn.execute('''
            UPDATE users SET credits = credits + ?, total_earned = total_earned + ?,
                           ads_today = ads_today + 1, last_ad_time = ?, last_ad_date = ?
            WHERE user_id = ?
        ''', (reward, reward, current_time_str, today, uid))
        
        # Update ad views
        if conn.execute('''
            SELECT 1 FROM user_ad_views WHERE user_id = ? AND ad_key = ? AND last_view_date = ?
        ''', (uid, ad_key, today)).fetchone():
            conn.execute('''
                UPDATE user_ad_views SET views_today = views_today + 1, total_views = total_views + 1
                WHERE user_id = ? AND ad_key = ? AND last_view_date = ?
            ''', (uid, ad_key, today))
        else:
            conn.execute('''
                INSERT INTO user_ad_views (user_id, ad_key, views_today, last_view_date, total_views)
                VALUES (?, ?, 1, ?, 1)
            ''', (uid, ad_key, today))
        
        # Add to history
        date = datetime.now().strftime("%b %d, %Y")
        ad_name = ad_config.get('name', ad_key)
        conn.execute('''
            INSERT INTO history (user_id, item_name, price, date, type)
            VALUES (?, ?, ?, ?, ?)
        ''', (uid, f'📺 {ad_name}', reward, date, 'earn'))
        
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

# New: Get purchases only
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

# New: Get specific history item
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

# Ad networks endpoints
@app.route('/api/admin/get_ad_networks')
def get_ad_networks():
    conn = get_db()
    
    try:
        rows = conn.execute('SELECT * FROM ad_networks ORDER BY created_at DESC').fetchall()
        networks = {}
        
        for row in rows:
            networks[row['ad_key']] = {
                'name': row['name'],
                'type': row['type'],
                'script_url': row['script_url'],
                'zone_id': row['zone_id'],
                'reward': row['reward'],
                'daily_limit': row['daily_limit'],
                'description': row['description'],
                'active': bool(row['active'])
            }
        
        return jsonify({
            'success': True,
            'ad_networks': networks
        })
        
    except Exception as e:
        logger.error(f"Get ad networks error: {e}")
        return jsonify({'success': False, 'message': 'Server error'}), 500
        
    finally:
        conn.close()

@app.route('/api/admin/manage_ad_network', methods=['POST'])
def manage_ad_network():
    data = request.json
    if not check_admin_auth(data):
        logger.error(f"Admin auth failed for user {data.get('admin_id')}")
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    action = data.get('action')
    conn = get_db()
    
    try:
        if action == 'add':
            ad_network = data.get('ad_network')
            if not ad_network:
                return jsonify({'success': False, 'message': 'No ad network data'}), 400
            
            # Generate ad key from name if not provided
            ad_key = ad_network.get('ad_key')
            if not ad_key:
                ad_key = ad_network['name'].lower().replace(' ', '_')
            
            # Check if ad key already exists
            existing = conn.execute('SELECT 1 FROM ad_networks WHERE ad_key = ?', (ad_key,)).fetchone()
            if existing:
                # Update existing
                conn.execute('''
                    UPDATE ad_networks SET 
                        name = ?, type = ?, script_url = ?, zone_id = ?, 
                        reward = ?, daily_limit = ?, description = ?, active = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE ad_key = ?
                ''', (
                    ad_network.get('name', ad_key),
                    ad_network.get('type', 'popup'),
                    ad_network.get('script_url'),
                    ad_network.get('zone_id'),
                    ad_network.get('reward', 4),
                    ad_network.get('daily_limit'),
                    ad_network.get('description', ''),
                    ad_network.get('active', True),
                    ad_key
                ))
            else:
                # Insert new
                conn.execute('''
                    INSERT INTO ad_networks 
                    (ad_key, name, type, script_url, zone_id, reward, daily_limit, description, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    ad_key,
                    ad_network.get('name', ad_key),
                    ad_network.get('type', 'popup'),
                    ad_network.get('script_url'),
                    ad_network.get('zone_id'),
                    ad_network.get('reward', 4),
                    ad_network.get('daily_limit'),
                    ad_network.get('description', ''),
                    ad_network.get('active', True)
                ))
            
            conn.commit()
            
            # Update global AD_NETWORKS
            update_ad_networks_global()
            
            return jsonify({
                'success': True, 
                'message': f'Ad network "{ad_key}" {"updated" if existing else "added"} successfully',
                'ad_key': ad_key
            })
        
        elif action == 'toggle':
            ad_key = data.get('ad_key')
            if not ad_key:
                return jsonify({'success': False, 'message': 'No ad key provided'}), 400
            
            # Get current status
            current = conn.execute('SELECT active FROM ad_networks WHERE ad_key = ?', (ad_key,)).fetchone()
            if not current:
                return jsonify({'success': False, 'message': 'Ad network not found'}), 404
            
            new_status = 0 if current['active'] else 1
            
            conn.execute('''
                UPDATE ad_networks SET active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE ad_key = ?
            ''', (new_status, ad_key))
            
            conn.commit()
            
            # Update global AD_NETWORKS
            update_ad_networks_global()
            
            return jsonify({
                'success': True,
                'message': f'Ad network "{ad_key}" {"enabled" if new_status else "disabled"}',
                'active': bool(new_status)
            })
        
        elif action == 'delete':
            ad_key = data.get('ad_key')
            confirm = data.get('confirm', False)
            
            if not ad_key:
                return jsonify({'success': False, 'message': 'No ad key provided'}), 400
            
            if not confirm:
                return jsonify({
                    'success': False,
                    'message': 'Confirmation required',
                    'requires_confirm': True
                }), 400
            
            # Delete ad network
            conn.execute('DELETE FROM ad_networks WHERE ad_key = ?', (ad_key,))
            
            # Also delete user ad views for this network
            conn.execute('DELETE FROM user_ad_views WHERE ad_key = ?', (ad_key,))
            
            conn.commit()
            
            # Update global AD_NETWORKS
            update_ad_networks_global()
            
            return jsonify({
                'success': True,
                'message': f'Ad network "{ad_key}" deleted successfully'
            })
        
        else:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
    except Exception as e:
        logger.error(f"Manage ad network error: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
        
    finally:
        conn.close()

# Admin routes
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
                UPDATE users SET ads_today = 0, last_ad_date = ?
                WHERE user_id = ?
            ''', (today, user_id))
            
            # Reset all ad views for this user
            conn.execute('''
                UPDATE user_ad_views SET views_today = 0, last_view_date = ?
                WHERE user_id = ?
            ''', (today, user_id))
            
            conn.commit()
            return jsonify({'success': True, 'message': f'Reset ads for user {user_id}'})
        
        elif action == 'reset_all_ads':
            today = datetime.now().strftime("%Y-%m-%d")
            
            conn.execute('''
                UPDATE users SET ads_today = 0, last_ad_date = ?
            ''', (today,))
            
            # Reset all ad views for all users
            conn.execute('''
                UPDATE user_ad_views SET views_today = 0, last_view_date = ?
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
            for ad_key in AD_NETWORKS.keys():
                total = conn.execute('SELECT SUM(total_views) FROM user_ad_views WHERE ad_key = ?', (ad_key,)).fetchone()[0] or 0
                ad_stats[ad_key] = total
            
            # Item stats
            total_items = conn.execute('SELECT COUNT(*) FROM items').fetchone()[0]
            total_sales = conn.execute('SELECT SUM(price * sold) FROM items').fetchone()[0] or 0
            
            # Revenue stats
            total_earned = conn.execute('SELECT SUM(total_earned) FROM users').fetchone()[0] or 0
            total_spent = conn.execute('SELECT SUM(total_spent) FROM users').fetchone()[0] or 0
            
            # Ad network stats
            ad_network_stats = {}
            rows = conn.execute('SELECT ad_key, COUNT(*) as users, SUM(total_views) as total_views FROM user_ad_views GROUP BY ad_key').fetchall()
            for row in rows:
                ad_network_stats[row['ad_key']] = {
                    'users': row['users'],
                    'total_views': row['total_views']
                }
            
            return jsonify({
                'success': True,
                'stats': {
                    'total_users': total_users,
                    'active_today': active_today,
                    'total_credits': total_credits,
                    'ad_stats': ad_stats,
                    'ad_network_stats': ad_network_stats,
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
            ad_networks = [dict(row) for row in conn.execute('SELECT * FROM ad_networks').fetchall()]
            user_ad_views = [dict(row) for row in conn.execute('SELECT * FROM user_ad_views').fetchall()]
            
            backup = {
                'timestamp': datetime.now().isoformat(),
                'users': users,
                'items': items,
                'history': history,
                'config': config,
                'ad_networks': ad_networks,
                'user_ad_views': user_ad_views
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
        
        return jsonify({
            'success': True,
            'recent_activity': [dict(row) for row in recent_activity],
            'top_earners': [dict(row) for row in top_earners],
            'popular_items': [dict(row) for row in popular_items]
        })
        
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return jsonify({'success': False, 'message': 'Server error'}), 500
        
    finally:
        conn.close()

# Admin login endpoint
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
            return jsonify({'success': True, 'message': 'Login successful'})
        else:
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
    except:
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

# Make user admin
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
    return jsonify({
        'status': 'ok',
        'service': 'Own Bazar',
        'timestamp': datetime.now().isoformat(),
        'database': 'connected',
        'version': '2.0.0',
        'ad_networks': len(AD_NETWORKS)
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
