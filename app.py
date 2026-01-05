import sqlite3
import os
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
ADMIN_ONLY_ID = int(os.environ.get('ADMIN_ID', '6068468333'))
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
    
    # Insert default config for ad networks
    defaults = []
    for ad_type, config in AD_NETWORKS.items():
        defaults.append((f'reward_{ad_type}', str(config['reward']), f'Reward for {ad_type} ads'))
        defaults.append((f'limit_{ad_type}', str(config['daily_limit']), f'Daily limit for {ad_type} ads'))
    
    # Additional defaults
    defaults.extend([
        ('welcome_bonus', '10', 'Welcome bonus for new users'),
        ('referral_bonus', '15', 'Bonus for referrals'),
        ('ad_cooldown', '10', 'Cooldown between ads in seconds')
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
    
    # Add admin user
    conn.execute(
        'INSERT OR IGNORE INTO users (user_id, first_name, username, credits, is_admin) VALUES (?, ?, ?, ?, ?)',
        (ADMIN_ONLY_ID, 'Admin', 'admin', 1000, 1)
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
        return admin_id == ADMIN_ONLY_ID and admin_pass == ADMIN_PASSWORD
    except:
        return False

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
        welcome_bonus = int(get_config().get('welcome_bonus', '10'))
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
    user_dict['is_admin'] = bool(user['is_admin']) or (uid == ADMIN_ONLY_ID)
    user_dict['config'] = get_config()
    
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
            
            cooldown = int(get_config().get('ad_cooldown', '10'))
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
        
        # Add to history
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

# Admin routes
@app.route('/api/admin/manage', methods=['POST'])
def admin_manage():
    if not check_admin_auth(request.json):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    action = data.get('action')
    conn = get_db()
    
    try:
        if action == 'add_credits':
            user_id = data.get('user_id')
            amount = data.get('amount', 0)
            
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
            
            conn.execute('''
                INSERT INTO items (name, category, price, stock, is_active, content, ip, link, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item_data.get('name'),
                item_data.get('category'),
                item_data.get('price'),
                item_data.get('stock', 999),
                item_data.get('is_active', 1),
                item_data.get('content'),
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

@app.route('/api/admin/dashboard', methods=['POST'])
def admin_dashboard():
    if not check_admin_auth(request.json):
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

# System routes
@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'service': 'Own Bazar',
        'timestamp': datetime.now().isoformat(),
        'database': 'connected',
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
