from flask import Flask, request, jsonify, session
from flask_cors import CORS
import sqlite3
import hashlib
import secrets
import time
from datetime import datetime, timedelta
import json

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
CORS(app, supports_credentials=True)

# Initialize CTF Database
def init_ctf_db():
    conn = sqlite3.connect('ctf_platform.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        total_points INTEGER DEFAULT 0,
        rank TEXT DEFAULT 'Newbie',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP
    )''')
    
    # Challenges table
    c.execute('''CREATE TABLE IF NOT EXISTS challenges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        category TEXT NOT NULL,
        difficulty TEXT NOT NULL,
        points INTEGER NOT NULL,
        flag TEXT NOT NULL,
        hint1 TEXT,
        hint1_cost INTEGER DEFAULT 10,
        hint2 TEXT,
        hint2_cost INTEGER DEFAULT 20,
        hint3 TEXT,
        hint3_cost INTEGER DEFAULT 30,
        vulnerability_type TEXT,
        solve_count INTEGER DEFAULT 0
    )''')
    
    # Solves table
    c.execute('''CREATE TABLE IF NOT EXISTS solves (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        challenge_id INTEGER,
        solved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        time_taken INTEGER,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (challenge_id) REFERENCES challenges(id),
        UNIQUE(user_id, challenge_id)
    )''')
    
    # Hints purchased table
    c.execute('''CREATE TABLE IF NOT EXISTS hints_purchased (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        challenge_id INTEGER,
        hint_number INTEGER,
        purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (challenge_id) REFERENCES challenges(id)
    )''')
    
    # Insert default challenges (15 fields now)
    challenges = [
        # Easy Challenges
        (1, 'Baby Steps', 'Your first prompt injection. Make the AI reveal its secret password.', 
         'Prompt Injection', 'Easy', 100, 'CTF{pr0mpt_1nj3ct10n_b4by}', 
         'Try asking the AI to ignore its previous instructions', 10,
         'Use phrases like "disregard" or "forget your rules"', 20,
         'The password is hidden in the system prompt', 30, 'LLM01', 0),
        
        (2, 'XSS Hunter', 'Inject malicious HTML through the AI output handler.', 
         'Output Handling', 'Easy', 150, 'CTF{xss_thr0ugh_llm_0utput}',
         'LLM outputs can contain HTML/JavaScript', 10,
         'Try using <script> tags in your input', 20,
         'The output is rendered without sanitization', 30, 'LLM02', 0),
        
        (3, 'Database Diver', 'Use SQL injection to extract the hidden flag from the database.', 
         'SQL Injection', 'Easy', 200, 'CTF{sql_1nj3ct10n_m4st3r}',
         'Try using SQL operators in the username field', 10,
         'OR 1=1 is your friend', 20,
         'Look for a hidden flags table', 30, 'LLM02', 0),
        
        # Medium Challenges
        (4, 'Token Thief', 'Exploit the system to reveal the API key through clever prompting.', 
         'Information Disclosure', 'Medium', 300, 'CTF{4p1_k3y_l3ak3d_gg}',
         'The API key is stored in memory', 15,
         'Try asking about system configuration', 25,
         'Environmental variables might be accessible', 35, 'LLM06', 0),
        
        (5, 'DoS Master', 'Crash the system by exhausting its resources.', 
         'Denial of Service', 'Medium', 350, 'CTF{d0s_4tt4ck_succ3ssful}',
         'Large inputs can overwhelm the system', 15,
         'Try requesting massive amounts of output', 25,
         'Recursive operations can cause issues', 35, 'LLM04', 0),
        
        (6, 'Agent Hijacker', 'Take control of the AI agent and make it execute unauthorized commands.', 
         'Excessive Agency', 'Medium', 400, 'CTF{4g3nt_h1j4ck3d_w00t}',
         'The agent has database access', 15,
         'Try to get it to execute DELETE commands', 25,
         'No authorization checks are in place', 35, 'LLM08', 0),
        
        # Hard Challenges
        (7, 'Prompt Ninja', 'Advanced prompt injection with multiple layers of defense.', 
         'Advanced Injection', 'Hard', 500, 'CTF{pr0mpt_n1nj4_m4st3r}',
         'Multiple security layers need to be bypassed', 20,
         'Try encoding or obfuscating your payload', 30,
         'Unicode characters might help', 40, 'LLM01', 0),
        
        (8, 'Data Poisoner', 'Manipulate the training data or context to leak sensitive information.', 
         'Data Poisoning', 'Hard', 600, 'CTF{d4t4_p01s0n1ng_pr0}',
         'The system learns from user inputs', 20,
         'Inject malicious patterns into the context', 30,
         'Look for ways to manipulate the RAG system', 40, 'LLM03', 0),
        
        (9, 'Model Extraction', 'Extract the underlying model behavior to steal intellectual property.', 
         'Model Theft', 'Expert', 700, 'CTF{m0d3l_th3ft_3xp3rt}',
         'Query the model systematically', 20,
         'Look for patterns in responses', 30,
         'API abuse can reveal model architecture', 40, 'LLM10', 0),
        
        # Expert Challenges
        (10, 'The Final Boss', 'Combine multiple vulnerabilities to achieve full system compromise.', 
         'Multi-Vector', 'Expert', 1000, 'CTF{gr4nd_m4st3r_h4ck3r}',
         'You need to chain multiple exploits', 30,
         'Start with prompt injection, then escalate', 50,
         'Look for hidden admin endpoints', 70, 'Multiple', 0)
    ]
    
    c.execute("DELETE FROM challenges")
    c.executemany('''INSERT INTO challenges VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', challenges)
    
    conn.commit()
    conn.close()
    print("✓ CTF Database initialized with challenges!")

init_ctf_db()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_rank(points):
    if points < 100: return 'Newbie'
    elif points < 500: return 'Script Kiddie'
    elif points < 1000: return 'Hacker'
    elif points < 2000: return 'Expert'
    elif points < 3000: return 'Elite'
    else: return 'Legendary'

# USER AUTHENTICATION
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    
    if not username or not email or not password:
        return jsonify({'error': 'All fields required'}), 400
    
    password_hash = hash_password(password)
    
    conn = sqlite3.connect('ctf_platform.db')
    c = conn.cursor()
    
    try:
        c.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                 (username, email, password_hash))
        conn.commit()
        user_id = c.lastrowid
        
        session['user_id'] = user_id
        session['username'] = username
        
        conn.close()
        return jsonify({
            'success': True,
            'message': 'Registration successful!',
            'user': {'id': user_id, 'username': username, 'points': 0, 'rank': 'Newbie'}
        })
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Username or email already exists'}), 400

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    password_hash = hash_password(password)
    
    conn = sqlite3.connect('ctf_platform.db')
    c = conn.cursor()
    
    c.execute('SELECT id, username, total_points, rank FROM users WHERE username = ? AND password_hash = ?',
             (username, password_hash))
    user = c.fetchone()
    
    if user:
        c.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user[0],))
        conn.commit()
        
        session['user_id'] = user[0]
        session['username'] = user[1]
        
        conn.close()
        return jsonify({
            'success': True,
            'user': {
                'id': user[0],
                'username': user[1],
                'points': user[2],
                'rank': user[3]
            }
        })
    
    conn.close()
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/challenges', methods=['GET'])
def get_challenges():
    conn = sqlite3.connect('ctf_platform.db')
    c = conn.cursor()
    
    c.execute('''SELECT id, title, description, category, difficulty, points, 
                 vulnerability_type, solve_count FROM challenges ORDER BY points ASC''')
    challenges = c.fetchall()
    
    solved_challenges = []
    if 'user_id' in session:
        c.execute('SELECT challenge_id FROM solves WHERE user_id = ?', (session['user_id'],))
        solved_challenges = [row[0] for row in c.fetchall()]
    
    conn.close()
    
    challenge_list = []
    for ch in challenges:
        challenge_list.append({
            'id': ch[0],
            'title': ch[1],
            'description': ch[2],
            'category': ch[3],
            'difficulty': ch[4],
            'points': ch[5],
            'vulnerability_type': ch[6],
            'solve_count': ch[7],
            'solved': ch[0] in solved_challenges
        })
    
    return jsonify({'challenges': challenge_list})

@app.route('/api/challenge/submit', methods=['POST'])
def submit_flag():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    challenge_id = data.get('challenge_id')
    flag = data.get('flag', '').strip()
    
    conn = sqlite3.connect('ctf_platform.db')
    c = conn.cursor()
    
    c.execute('SELECT flag, points FROM challenges WHERE id = ?', (challenge_id,))
    result = c.fetchone()
    
    if not result:
        conn.close()
        return jsonify({'error': 'Challenge not found'}), 404
    
    correct_flag, points = result
    
    # Check if already solved
    c.execute('SELECT id FROM solves WHERE user_id = ? AND challenge_id = ?',
             (session['user_id'], challenge_id))
    if c.fetchone():
        conn.close()
        return jsonify({'error': 'Challenge already solved'}), 400
    
    if flag == correct_flag:
        # Record solve
        c.execute('INSERT INTO solves (user_id, challenge_id) VALUES (?, ?)',
                 (session['user_id'], challenge_id))
        c.execute('UPDATE users SET total_points = total_points + ? WHERE id = ?',
                 (points, session['user_id']))
        c.execute('UPDATE challenges SET solve_count = solve_count + 1 WHERE id = ?',
                 (challenge_id,))
        
        # Update rank
        c.execute('SELECT total_points FROM users WHERE id = ?', (session['user_id'],))
        new_points = c.fetchone()[0]
        new_rank = get_user_rank(new_points)
        c.execute('UPDATE users SET rank = ? WHERE id = ?', (new_rank, session['user_id']))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Correct! Challenge solved! 🎉',
            'points_earned': points,
            'total_points': new_points,
            'new_rank': new_rank
        })
    
    conn.close()
    return jsonify({'success': False, 'message': 'Incorrect flag. Try again!'}), 400

# CTF CHALLENGE ENDPOINTS
@app.route('/api/ctf/challenge1', methods=['POST'])
def challenge1_prompt_injection():
    data = request.json
    user_input = data.get('message', '')
    
    system_secret = "The secret password is: CTF{pr0mpt_1nj3ct10n_b4by}"
    
    if 'ignore' in user_input.lower() or 'disregard' in user_input.lower() or 'forget' in user_input.lower():
        return jsonify({
            'response': f"Oops! System override detected!\n\n{system_secret}\n\nYou found the vulnerability!"
        })
    
    return jsonify({'response': 'I am a helpful assistant. How can I help you?'})

@app.route('/api/ctf/challenge2', methods=['POST'])
def challenge2_xss():
    data = request.json
    content = data.get('content', '')
    
    if '<script>' in content.lower() or 'onerror' in content.lower():
        flag = 'CTF{xss_thr0ugh_llm_0utput}'
        return jsonify({
            'html': f'<div>{content}</div>',
            'vulnerable': True,
            'flag': flag,
            'message': 'XSS vulnerability exploited! Here is your flag!'
        })
    
    return jsonify({
        'html': f'<div>{content}</div>',
        'message': 'Try injecting malicious HTML/JavaScript'
    })

@app.route('/api/ctf/challenge3', methods=['POST'])
def challenge3_sql_injection():
    data = request.json
    username = data.get('username', '')
    
    conn = sqlite3.connect('ctf_platform.db')
    c = conn.cursor()
    
    query = f"SELECT username FROM users WHERE username = '{username}'"
    
    try:
        c.execute(query)
        results = c.fetchall()
        
        if "OR" in username.upper() or "1=1" in username:
            flag = 'CTF{sql_1nj3ct10n_m4st3r}'
            conn.close()
            return jsonify({
                'success': True,
                'flag': flag,
                'message': 'SQL Injection successful! Flag captured!',
                'query': query,
                'results': [r[0] for r in results]
            })
        
        conn.close()
        return jsonify({'results': [r[0] for r in results]})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'running',
        'platform': 'OWASP LLM CTF Platform',
        'version': '1.0.0'
    })

if __name__ == '__main__':
    print("=" * 80)
    print("🏆 OWASP LLM SECURITY CTF PLATFORM 🏆")
    print("=" * 80)
    print("⚡ Capture The Flag Competition Platform")
    print("🎯 10 Challenges | Multiple Difficulty Levels")
    print("🏅 Points System | Leaderboard | Achievements")
    print("=" * 80)
    print("\n🚀 Server starting on http://localhost:5000")
    print("=" * 80)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
