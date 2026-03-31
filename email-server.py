#!/usr/bin/env python3
"""
Class2Career Email Capture Server
Handles: email subscriptions, lead magnet delivery, purchase webhooks
"""

import os
import json
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, redirect, send_file
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content

app = Flask(__name__)

# Configuration
DATABASE = 'subscribers.db'
SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')
FROM_EMAIL = 'ignis@biztranslation.com'

# Lead magnets mapping
LEAD_MAGNETS = {
    'phd-translation-guide': 'Business Translation Guide.pdf',
    'value-equation': 'Value Equation Worksheet.pdf', 
    'corporate-toolkit': 'Corporate Toolkit.pdf'
}

# Initialize database
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            lead_magnet TEXT,
            source TEXT,
            utm_source TEXT,
            utm_medium TEXT,
            utm_campaign TEXT,
            subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active',
            UNIQUE(email)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS email_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Send email via SendGrid
def send_email(to_email, subject, html_content):
    if not SENDGRID_API_KEY:
        print(f"WARNING: SENDGRID_API_KEY not set. Email would be sent to {to_email}")
        print(f"Subject: {subject}")
        return False
    
    try:
        sg = sendgrid.SendGridAPIClient(SENDGRID_API_KEY)
        message = Mail(
            from_email=FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            html_content=html_content
        )
        response = sg.send(message)
        print(f"Email sent to {to_email}: {response.status_code}")
        return response.status_code == 200 or response.status_code == 202
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

# Log event
def log_event(email, event_type, event_data=None):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute(
        'INSERT INTO email_events (email, event_type, event_data) VALUES (?, ?, ?)',
        (email, event_type, json.dumps(event_data) if event_data else None)
    )
    conn.commit()
    conn.close()

# Routes

@app.route('/')
def index():
    return redirect('https://class2careers.com')

@app.route('/subscribe', methods=['POST'])
def subscribe():
    data = request.form
    email = data.get('email', '').strip().lower()
    lead_magnet = data.get('lead_magnet', '')
    source = data.get('source', 'website')
    utm_source = data.get('utm_source', '')
    utm_medium = data.get('utm_medium', '')
    utm_campaign = data.get('utm_campaign', '')
    
    if not email or '@' not in email:
        return jsonify({'error': 'Valid email required'}), 400
    
    # Save to database
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO subscribers (email, lead_magnet, source, utm_source, utm_medium, utm_campaign)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (email, lead_magnet, source, utm_source, utm_medium, utm_campaign))
        conn.commit()
        new_subscriber = True
    except sqlite3.IntegrityError:
        # Email already exists
        c.execute('SELECT * FROM subscribers WHERE email = ?', (email,))
        new_subscriber = False
    
    # Get lead magnet filename
    magnet_filename = LEAD_MAGNETS.get(lead_magnet, '')
    
    # Get subscriber info for email
    result = c.execute('SELECT * FROM subscribers WHERE email = ?', (email,)).fetchone()
    conn.close()
    
    if new_subscriber:
        # Send welcome email with lead magnet
        if magnet_filename:
            subject = f'Your free guide: {magnet_filename.replace(".pdf", "")}'
            html_content = f'''
            <h1>Welcome to Class2Career!</h1>
            <p>Thanks for signing up. Here's your free guide: <strong>{magnet_filename.replace(".pdf", "")}</strong></p>
            <p>Check the attachment to get started.</p>
            <hr>
            <p>Stay tuned for more tips on transitioning to business.</p>
            <p>Best,<br>Ignis Spindler, PhD</p>
            '''
            # In production, attach the actual PDF
            send_email(email, subject, html_content)
        
        log_event(email, 'subscribed', {'lead_magnet': lead_magnet})
        return jsonify({'success': True, 'message': 'Welcome! Check your inbox.'}), 200
    else:
        log_event(email, 'duplicate_subscription', {'lead_magnet': lead_magnet})
        return jsonify({'success': True, 'message': 'Already subscribed!'}), 200

@app.route('/lead-magnet/<filename>')
def get_lead_magnet(filename):
    """Download lead magnet file"""
    magnet_path = f'lead_magnets/{filename}'
    if os.path.exists(magnet_path):
        return send_file(magnet_path, as_attachment=True)
    return jsonify({'error': 'File not found'}), 404

@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    """Handle Stripe purchase events"""
    payload = request.data
    sig = request.headers.get('Stripe-Signature')
    
    # In production: verify Stripe signature
    # event = stripe.Webhook.construct_event(payload, sig, webhook_secret)
    
    try:
        event = json.loads(payload)
    except:
        return jsonify({'error': 'Invalid payload'}), 400
    
    event_type = event.get('type')
    
    if event_type == 'checkout.session.completed':
        email = event['data']['object'].get('customer_email')
        if email:
            # Update subscriber status to customer
            conn = sqlite3.connect(DATABASE)
            c = conn.cursor()
            c.execute('''
                UPDATE subscribers 
                SET status = 'customer', purchased_at = CURRENT_TIMESTAMP
                WHERE email = ?
            ''', (email,))
            conn.commit()
            conn.close()
            log_event(email, 'purchase', event['data']['object'])
            
            # Send confirmation email
            subject = 'Your Class2Career Toolkit is Ready!'
            html_content = '''
            <h1>Welcome to Class2Career!</h1>
            <p>Thank you for your purchase. Your toolkit is attached.</p>
            <p>Questions? Reply to this email anytime.</p>
            <p>Best,<br>Ignis Spindler, PhD</p>
            '''
            send_email(email, subject, html_content)
    
    return jsonify({'success': True}), 200

@app.route('/subscribers')
def list_subscribers():
    """Admin endpoint - list all subscribers (protected in production)"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    rows = c.execute('SELECT * FROM subscribers ORDER BY subscribed_at DESC').fetchall()
    conn.close()
    
    subscribers = []
    for row in rows:
        subscribers.append({
            'id': row[0],
            'email': row[1],
            'lead_magnet': row[2],
            'source': row[3],
            'utm_source': row[4],
            'subscribed_at': row[7],
            'status': row[9]
        })
    
    return jsonify(subscribers)

@app.route('/stats')
def stats():
    """Admin endpoint - get subscriber stats"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    total = c.execute('SELECT COUNT(*) FROM subscribers').fetchone()[0]
    customers = c.execute("SELECT COUNT(*) FROM subscribers WHERE status = 'customer'").fetchone()[0]
    by_source = c.execute('''
        SELECT utm_source, COUNT(*) as count 
        FROM subscribers 
        WHERE utm_source IS NOT NULL AND utm_source != ''
        GROUP BY utm_source
    ''').fetchall()
    by_magnet = c.execute('''
        SELECT lead_magnet, COUNT(*) as count 
        FROM subscribers 
        WHERE lead_magnet IS NOT NULL AND lead_magnet != ''
        GROUP BY lead_magnet
    ''').fetchall()
    
    conn.close()
    
    return jsonify({
        'total_subscribers': total,
        'total_customers': customers,
        'by_utm_source': [{'source': r[0], 'count': r[1]} for r in by_source],
        'by_lead_magnet': [{'magnet': r[0], 'count': r[1]} for r in by_magnet]
    })

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
