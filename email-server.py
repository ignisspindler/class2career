"""
email-server.py — Class2Career Email Capture & Lead Delivery
Handles: /subscribe (email capture + guide delivery), /webhook/stripe (payment)
"""
import os
import sqlite3
import sendgrid
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), 'leads.db')

# ─── SendGrid Client ─────────────────────────────────────────────────────────
def get_sg_client():
    api_key = os.environ.get('SENDGRID_API_KEY', '')
    return SendGridAPIClient(api_key)

# ─── Interview Guide HTML (inline email) ─────────────────────────────────────
INTERVIEW_GUIDE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The Interview Mastery System</title>
</head>
<body style="margin:0;padding:0;background:#0A0E1A;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;color:#FAF7F0;">
    <div style="max-width:600px;margin:0 auto;padding:40px 20px;background:#0A0E1A;">

        <!-- Header -->
        <div style="text-align:center;padding-bottom:30px;border-bottom:1px solid rgba(232,184,75,0.2);">
            <h1 style="font-family:Georgia,serif;font-size:28px;color:#E8B84B;margin:0 0 10px;">The Interview Mastery System</h1>
            <p style="color:#9CA3AF;font-size:14px;margin:0;">30 Days to Your Next Job — Free Guide from Class2Career</p>
        </div>

        <!-- Intro -->
        <div style="padding:30px 0;">
            <p style="font-size:16px;line-height:1.7;color:#D4CEC3;margin:0 0 20px;">
                Thanks for downloading the Interview Mastery System. This guide gives you the exact 30-day system I used to transition from academia to industry — and ultimately into management at companies where I was earning multiples of what my PhD peers thought was "the going rate."
            </p>
            <p style="font-size:16px;line-height:1.7;color:#D4CEC3;margin:0 0 20px;">
                <strong style="color:#E8B84B;">The uncomfortable truth:</strong> The interview isn't a test of your expertise. It's a test of your ability to translate your expertise into business value. Most candidates walk in describing what they did. You need to walk in describing what you'll do <em>for them</em>.
            </p>
        </div>

        <!-- The 30-Day System -->
        <div style="background:#111827;border-radius:12px;padding:30px;margin-bottom:30px;border:1px solid rgba(232,184,75,0.15);">
            <h2 style="font-family:Georgia,serif;font-size:22px;color:#E8B84B;margin:0 0 20px;">The 30-Day System</h2>

            <div style="margin-bottom:25px;">
                <h3 style="font-size:14px;text-transform:uppercase;letter-spacing:0.1em;color:#9CA3AF;margin:0 0 8px;">Days 1-7: Research</h3>
                <p style="font-size:14px;line-height:1.6;color:#D4CEC3;margin:0;">Company fundamentals, market position, competitive landscape. Find who will hire you and study their LinkedIn history. Identify the 3 competitors you'd face and what market share means for each.</p>
            </div>

            <div style="margin-bottom:25px;">
                <h3 style="font-size:14px;text-transform:uppercase;letter-spacing:0.1em;color:#9CA3AF;margin:0 0 8px;">Days 8-14: Self-Assessment</h3>
                <p style="font-size:14px;line-height:1.6;color:#D4CEC3;margin:0;">Translate every major experience into the four business currencies: Revenue, Cost, Time, Scale. Rewrite your resume in the language of business — not the language of academia.</p>
            </div>

            <div style="margin-bottom:25px;">
                <h3 style="font-size:14px;text-transform:uppercase;letter-spacing:0.1em;color:#9CA3AF;margin:0 0 8px;">Days 15-21: Interview Preparation</h3>
                <p style="font-size:14px;line-height:1.6;color:#D4CEC3;margin:0;">Prepare 5 questions to ask every interviewer that demonstrate research. Master the STAR method — but know when to skip it. Practice your 60-second metric story until it sounds natural.</p>
            </div>

            <div style="margin-bottom:25px;">
                <h3 style="font-size:14px;text-transform:uppercase;letter-spacing:0.1em;color:#9CA3AF;margin:0 0 8px;">Days 22-28: Execution</h3>
                <p style="font-size:14px;line-height:1.6;color:#D4CEC3;margin:0;">The 80/20 rule: 20% of what you say determines 80% of the outcome. Anchor every answer in a metric. Signal leadership in every answer — even when not asked directly.</p>
            </div>

            <div>
                <h3 style="font-size:14px;text-transform:uppercase;letter-spacing:0.1em;color:#9CA3AF;margin:0 0 8px;">Days 29-30: Follow-Up & Negotiation</h3>
                <p style="font-size:14px;line-height:1.6;color:#D4CEC3;margin:0;">Send the 4-sentence follow-up email within 24 hours. Know what to negotiate (base, signing bonus, equity, title) and what not to (benefits, remote policy before an offer).</p>
            </div>
        </div>

        <!-- Business Translation Cheat Sheet -->
        <div style="padding:0 0 30px;">
            <h2 style="font-family:Georgia,serif;font-size:22px;color:#E8B84B;margin:0 0 20px;">The Business Translation Cheat Sheet</h2>
            <p style="font-size:14px;line-height:1.7;color:#D4CEC3;margin:0 0 15px;">Translate academic language into business language:</p>

            <table style="width:100%;border-collapse:collapse;font-size:13px;">
                <tr style="border-bottom:1px solid rgba(232,184,75,0.2);">
                    <td style="padding:10px 0;color:#9CA3AF;">Instead of...</td>
                    <td style="padding:10px 0;color:#E8B84B;font-weight:bold;">Say...</td>
                </tr>
                <tr style="border-bottom:1px solid rgba(232,184,75,0.1);">
                    <td style="padding:10px 0;color:#9CA3AF;">"I conducted research"</td>
                    <td style="padding:10px 0;color:#FAF7F0;">"I designed and executed an analysis that produced [specific finding]"</td>
                </tr>
                <tr style="border-bottom:1px solid rgba(232,184,75,0.1);">
                    <td style="padding:10px 0;color:#9CA3AF;">"I managed a team"</td>
                    <td style="padding:10px 0;color:#FAF7F0;">"I led a team of [X], coordinating [what] to achieve [outcome]"</td>
                </tr>
                <tr style="border-bottom:1px solid rgba(232,184,75,0.1);">
                    <td style="padding:10px 0;color:#9CA3AF;">"I published papers"</td>
                    <td style="padding:10px 0;color:#FAF7F0;">"My work was cited [X] times and influenced [industry] practice"</td>
                </tr>
                <tr style="border-bottom:1px solid rgba(232,184,75,0.1);">
                    <td style="padding:10px 0;color:#9CA3AF;">"I taught students"</td>
                    <td style="padding:10px 0;color:#FAF7F0;">"I developed curriculum that [specific measurable outcome]"</td>
                </tr>
                <tr>
                    <td style="padding:10px 0;color:#9CA3AF;">"I improved a process"</td>
                    <td style="padding:10px 0;color:#FAF7F0;">"I redesigned [process], reducing [metric] by [X%]"</td>
                </tr>
            </table>
        </div>

        <!-- Questions to Ask Section -->
        <div style="background:#111827;border-radius:12px;padding:30px;margin-bottom:30px;border:1px solid rgba(232,184,75,0.15);">
            <h2 style="font-family:Georgia,serif;font-size:22px;color:#E8B84B;margin:0 0 15px;">Questions That Signal You're a Top Candidate</h2>
            <p style="font-size:14px;line-height:1.6;color:#D4CEC3;margin:0 0 15px;">Ask these to show you've done your homework:</p>
            <ul style="font-size:14px;line-height:1.8;color:#D4CEC3;padding-left:20px;margin:0;">
                <li>"I read that [Company] grew [X]% — what's driving that, and where do you see it in 12 months?"</li>
                <li>"What's the current market share versus [competitor], and where do you see that moving?"</li>
                <li>"If I succeed spectacularly in 18 months, what would be different in the company?"</li>
                <li>"Can you tell me about the team I'd work with most closely? What's the dynamic?"</li>
                <li>"What are the 2-3 biggest challenges someone in this role faces in their first 30 days?"</li>
            </ul>
        </div>

        <!-- CTA -->
        <div style="text-align:center;padding:20px 0 40px;">
            <p style="font-size:15px;color:#9CA3AF;margin:0 0 20px;">Want the complete toolkit? All 5 workbooks that teach you to speak the language of business — without the $125K MBA.</p>
            <a href="https://class2careers.com" style="display:inline-block;background:#E8B84B;color:#0A0E1A;padding:14px 28px;font-weight:bold;font-size:15px;text-decoration:none;border-radius:8px;">Get the Complete Toolkit — $27</a>
        </div>

        <!-- Footer -->
        <div style="border-top:1px solid rgba(232,184,75,0.2);padding-top:25px;text-align:center;">
            <p style="font-size:12px;color:#6B7280;margin:0 0 8px;">© 2026 Class2Career | By Ignis Spindler, PhD</p>
            <p style="font-size:11px;color:#4B5563;margin:0;">You're receiving this because you subscribed at class2careers.com</p>
        </div>
    </div>
</body>
</html>
"""

# ─── Plain text version of the guide (for email clients that don't render HTML) ───
INTERVIEW_GUIDE_TEXT = """
THE INTERVIEW MASTERY SYSTEM
30 Days to Your Next Job — Free Guide from Class2Career
by Ignis Spindler, PhD

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Thanks for downloading the Interview Mastery System. This guide gives you the exact 30-day system I used to transition from academia to industry.

The uncomfortable truth: The interview isn't a test of your expertise. It's a test of your ability to translate your expertise into business value.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

THE 30-DAY SYSTEM

Days 1-7: Research
Company fundamentals, market position, competitive landscape. Find who will hire you and study their LinkedIn. Identify their 3 competitors and understand market share dynamics.

Days 8-14: Self-Assessment
Translate every major experience into the four business currencies: Revenue, Cost, Time, Scale. Rewrite your resume in the language of business — not academia.

Days 15-21: Interview Preparation
Prepare 5 questions that demonstrate research. Master the STAR method — but know when to skip it. Practice your 60-second metric story.

Days 22-28: Execution
The 80/20 rule: 20% of what you say determines 80% of the outcome. Anchor every answer in a metric. Signal leadership in every answer.

Days 29-30: Follow-Up & Negotiation
Send the 4-sentence follow-up email within 24 hours. Know what to negotiate (base, signing bonus, equity, title) and what not to.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BUSINESS TRANSLATION CHEAT SHEET

Instead of...                    Say...
"I conducted research"            "I designed and executed an analysis that produced [specific finding]"
"I managed a team"              "I led a team of [X], achieving [outcome]"
"I published papers"             "My work was cited [X] times, influencing [industry] practice"
"I taught students"              "I developed curriculum that [specific measurable outcome]"
"I improved a process"           "I redesigned [process], reducing [metric] by [X%]"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

QUESTIONS THAT SIGNAL TOP CANDIDATE

• "I read that [Company] grew [X]% — what's driving that, and where do you see it in 12 months?"
• "What's the current market share versus [competitor], and where do you see that moving?"
• "If I succeed spectacularly in 18 months, what would be different in the company?"
• "Can you tell me about the team I'd work with most closely? What's the dynamic?"
• "What are the 2-3 biggest challenges someone in this role faces in their first 30 days?"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Want the complete toolkit? All 5 workbooks that teach you to speak the language of business:
→ https://class2careers.com

© 2026 Class2Career | By Ignis Spindler, PhD
You received this because you subscribed at class2careers.com
"""

# ─── Database Helpers ─────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            lead_magnet TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            utm_source TEXT DEFAULT '',
            utm_medium TEXT DEFAULT '',
            utm_campaign TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_lead(email, lead_magnet='', source_url='', utm_source='', utm_medium='', utm_campaign=''):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO leads (email, lead_magnet, source_url, utm_source, utm_medium, utm_campaign)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (email, lead_magnet, source_url, utm_source, utm_medium, utm_campaign))
    conn.commit()
    new_subscriber = cur.rowcount > 0  # True if inserted, False if already existed
    conn.close()
    return new_subscriber

# ─── Email Sending ────────────────────────────────────────────────────────────
def send_guide_email(to_email):
    sg = get_sg_client()
    from_email = Email("ignis@biztranslation.com")
    to_email = To(to_email)
    subject = "Your Interview Mastery Guide — Here's What's Next"
    
    mail = Mail(from_email, to_email, subject)
    mail.reply_to = Email("ignis@biztranslation.com")
    
    # Send both HTML and plain text
    mail.add_content(Content("text/plain", INTERVIEW_GUIDE_TEXT))
    mail.add_content(Content("text/html", INTERVIEW_GUIDE_HTML))
    
    try:
        response = sg.send(mail)
        return response.status_code in [200, 201, 202]
    except Exception as e:
        print(f"SendGrid error: {e}")
        return False

# ─── Routes ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return """
    <html>
    <head><title>Email Captured</title></head>
    <body style="font-family:Helvetica,Arial,sans-serif;max-width:500px;margin:60px auto;padding:40px;background:#0A0E1A;color:#FAF7F0;text-align:center;border-radius:12px;border:1px solid rgba(232,184,75,0.3);">
        <h1 style="color:#E8B84B;font-size:24px;margin-bottom:15px;">You're on the list!</h1>
        <p style="color:#9CA3AF;font-size:16px;line-height:1.6;">Check your inbox — your Interview Mastery Guide is on its way. Also, expect weekly career tips from Class2Career.</p>
    </body>
    </html>
    """

@app.route("/subscribe", methods=["POST"])
def subscribe():
    email = request.form.get("email", "").strip().lower()
    lead_magnet = request.form.get("lead_magnet", "")
    
    if not email or "@" not in email:
        return jsonify({"error": "Valid email required"}), 400
    
    # UTM params from URL (if passed as form fields)
    utm_source = request.form.get("utm_source", "")
    utm_medium = request.form.get("utm_medium", "")
    utm_campaign = request.form.get("utm_campaign", "")
    
    # Referrer
    source_url = request.referrer or ""
    
    # Save to DB
    new_lead = save_lead(email, lead_magnet, source_url, utm_source, utm_medium, utm_campaign)
    
    # Send the guide
    if new_lead and lead_magnet:
        email_sent = send_guide_email(email)
        print(f"Lead {email} | new={new_lead} | guide_sent={email_sent}")
    else:
        print(f"Lead {email} | new={new_lead} | skipped_send (duplicate or no guide)")
    
    return """
    <html>
    <head><title>You're In!</title></head>
    <body style="font-family:Helvetica,Arial,sans-serif;max-width:500px;margin:60px auto;padding:40px;background:#0A0E1A;color:#FAF7F0;text-align:center;border-radius:12px;border:1px solid rgba(232,184,75,0.3);">
        <h1 style="color:#E8B84B;font-size:24px;margin-bottom:15px;">Check your inbox!</h1>
        <p style="color:#9CA3AF;font-size:16px;line-height:1.6;">Your Interview Mastery Guide is on its way. Check your spam folder if you don't see it within 2 minutes.</p>
    </body>
    </html>
    """

@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    # Placeholder for Stripe payment webhook
    return jsonify({"status": "ok"}), 200

# ─── Init ─────────────────────────────────────────────────────────────────────
if __name__ != "__main__":
    init_db()

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
