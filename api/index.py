"""
api/index.py — Class2Career Backend
Routes: /subscribe, /webhook/stripe, /access
Storage: Upstash Redis (persistent, serverless-native)
Email:   SendGrid
Payments: Stripe Webhooks
"""
import os
import json
import secrets
import urllib.request
import stripe as stripe_lib
from flask import Flask, request, jsonify, abort, make_response
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

app = Flask(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────
UPSTASH_URL           = os.environ.get('UPSTASH_REDIS_REST_URL', '')
UPSTASH_TOKEN         = os.environ.get('UPSTASH_REDIS_REST_TOKEN', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
SENDGRID_KEY          = os.environ.get('SENDGRID_API_KEY', '')
FROM_EMAIL            = 'ignis@biztranslation.com'
SITE_URL              = os.environ.get('SITE_URL', 'https://class2careers.com')

stripe_lib.api_key = os.environ.get('STRIPE_SECRET_KEY', '')

# ─── Upstash Redis ─────────────────────────────────────────────────────────────
def _redis(*cmd):
    """Execute one Redis command via Upstash REST pipeline."""
    payload = json.dumps([list(cmd)]).encode()
    req = urllib.request.Request(
        f"{UPSTASH_URL}/pipeline", data=payload, method='POST'
    )
    req.add_header('Authorization', f'Bearer {UPSTASH_TOKEN}')
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())[0].get('result')
    except Exception as e:
        print(f"[Redis error] {type(e).__name__}: {e}")
        return None

def r_set(key, value, ex=None):
    cmd = ['SET', key, json.dumps(value)]
    if ex:
        cmd += ['EX', str(ex)]
    return _redis(*cmd)

def r_get(key):
    raw = _redis('GET', key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return raw

def r_sadd(key, member):
    return _redis('SADD', key, member)

# ─── Lead & Purchase Storage ───────────────────────────────────────────────────
def save_lead(email, **meta):
    """Store lead; returns True if new, False if already captured."""
    key = f'lead:{email}'
    if r_get(key):
        return False
    r_set(key, {'email': email, **meta})
    r_sadd('leads:all', email)
    return True

def save_purchase(email, session_id, token):
    r_set(f'purchase:{email}', {'email': email, 'session_id': session_id, 'token': token})
    r_set(f'token:{token}', {'email': email, 'valid': True})
    r_sadd('purchases:all', email)

# ─── Email Helpers ─────────────────────────────────────────────────────────────
def _send(to_email, subject, html, text):
    sg = SendGridAPIClient(SENDGRID_KEY)
    msg = Mail(Email(FROM_EMAIL), To(to_email), subject)
    msg.reply_to = Email(FROM_EMAIL)
    msg.add_content(Content('text/plain', text))
    msg.add_content(Content('text/html', html))
    try:
        r = sg.send(msg)
        return r.status_code in [200, 201, 202]
    except Exception as e:
        print(f"[SendGrid error] {type(e).__name__}: {e}")
        return False

# ─── Lead Magnet Email ─────────────────────────────────────────────────────────
_LEAD_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0A0E1A;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;color:#FAF7F0;">
<div style="max-width:600px;margin:0 auto;padding:40px 20px;">

  <div style="text-align:center;padding-bottom:30px;border-bottom:1px solid rgba(232,184,75,0.2);">
    <h1 style="font-family:Georgia,serif;font-size:26px;color:#E8B84B;margin:0 0 8px;">The Interview Mastery System</h1>
    <p style="color:#9CA3AF;font-size:13px;margin:0;">30 Days to Your Next Job &mdash; Free Guide from Class2Career</p>
  </div>

  <div style="padding:30px 0;">
    <p style="font-size:16px;line-height:1.7;color:#D4CEC3;margin:0 0 18px;">
      Thanks for downloading the Interview Mastery System. This guide gives you the exact 30-day system I used to transition from academia to industry.
    </p>
    <p style="font-size:16px;line-height:1.7;color:#D4CEC3;margin:0 0 18px;">
      <strong style="color:#E8B84B;">The uncomfortable truth:</strong> The interview isn't a test of your expertise. It's a test of your ability to translate your expertise into business value.
    </p>
  </div>

  <div style="background:#111827;border-radius:12px;padding:28px;margin-bottom:28px;border:1px solid rgba(232,184,75,0.15);">
    <h2 style="font-family:Georgia,serif;font-size:20px;color:#E8B84B;margin:0 0 18px;">The 30-Day System</h2>
    <div style="margin-bottom:20px;">
      <p style="font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:#9CA3AF;margin:0 0 6px;">Days 1&ndash;7: Research</p>
      <p style="font-size:14px;line-height:1.6;color:#D4CEC3;margin:0;">Company fundamentals, market position, competitive landscape. Find who will hire you and study their LinkedIn history.</p>
    </div>
    <div style="margin-bottom:20px;">
      <p style="font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:#9CA3AF;margin:0 0 6px;">Days 8&ndash;14: Self-Assessment</p>
      <p style="font-size:14px;line-height:1.6;color:#D4CEC3;margin:0;">Translate every major experience into the four business currencies: Revenue, Cost, Time, Scale. Rewrite your resume in the language of business.</p>
    </div>
    <div style="margin-bottom:20px;">
      <p style="font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:#9CA3AF;margin:0 0 6px;">Days 15&ndash;21: Interview Prep</p>
      <p style="font-size:14px;line-height:1.6;color:#D4CEC3;margin:0;">Prepare 5 questions to ask every interviewer. Master the STAR method &mdash; but know when to skip it. Practice your 60-second metric story.</p>
    </div>
    <div style="margin-bottom:20px;">
      <p style="font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:#9CA3AF;margin:0 0 6px;">Days 22&ndash;28: Execution</p>
      <p style="font-size:14px;line-height:1.6;color:#D4CEC3;margin:0;">Anchor every answer in a metric. Signal leadership in every response &mdash; even when not asked directly.</p>
    </div>
    <div>
      <p style="font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:#9CA3AF;margin:0 0 6px;">Days 29&ndash;30: Follow-Up &amp; Negotiation</p>
      <p style="font-size:14px;line-height:1.6;color:#D4CEC3;margin:0;">Send the 4-sentence follow-up email within 24 hours. Know what to negotiate and what not to.</p>
    </div>
  </div>

  <div style="padding:0 0 28px;">
    <h2 style="font-family:Georgia,serif;font-size:20px;color:#E8B84B;margin:0 0 14px;">Business Translation Cheat Sheet</h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <tr style="border-bottom:1px solid rgba(232,184,75,0.2);"><td style="padding:10px 0;color:#9CA3AF;width:45%%">Instead of...</td><td style="padding:10px 0;color:#E8B84B;font-weight:bold;">Say...</td></tr>
      <tr style="border-bottom:1px solid rgba(232,184,75,0.08);"><td style="padding:9px 0;color:#9CA3AF;">"I conducted research"</td><td style="padding:9px 0;color:#FAF7F0;">"I designed an analysis that produced [specific finding]"</td></tr>
      <tr style="border-bottom:1px solid rgba(232,184,75,0.08);"><td style="padding:9px 0;color:#9CA3AF;">"I managed a team"</td><td style="padding:9px 0;color:#FAF7F0;">"I led [X] people to achieve [outcome]"</td></tr>
      <tr style="border-bottom:1px solid rgba(232,184,75,0.08);"><td style="padding:9px 0;color:#9CA3AF;">"I published papers"</td><td style="padding:9px 0;color:#FAF7F0;">"My work was cited [X] times, influencing [industry]"</td></tr>
      <tr style="border-bottom:1px solid rgba(232,184,75,0.08);"><td style="padding:9px 0;color:#9CA3AF;">"I taught students"</td><td style="padding:9px 0;color:#FAF7F0;">"I developed curriculum that [measurable outcome]"</td></tr>
      <tr><td style="padding:9px 0;color:#9CA3AF;">"I improved a process"</td><td style="padding:9px 0;color:#FAF7F0;">"I redesigned [process], reducing [metric] by [X%%]"</td></tr>
    </table>
  </div>

  <div style="text-align:center;padding:20px 0 36px;">
    <p style="font-size:15px;color:#9CA3AF;margin:0 0 18px;">Want the complete toolkit? All 5 workbooks that teach you to speak the language of business.</p>
    <a href="%(site_url)s" style="display:inline-block;background:#E8B84B;color:#0A0E1A;padding:14px 28px;font-weight:bold;font-size:15px;text-decoration:none;border-radius:8px;">Get the Complete Toolkit &mdash; $27</a>
  </div>

  <div style="border-top:1px solid rgba(232,184,75,0.15);padding-top:20px;text-align:center;">
    <p style="font-size:12px;color:#6B7280;margin:0 0 6px;">&copy; 2026 Class2Career | By Ignis Spindler, PhD</p>
    <p style="font-size:11px;color:#4B5563;margin:0;">You're receiving this because you signed up at class2careers.com</p>
  </div>
</div>
</body>
</html>"""

_LEAD_TEXT = """\
THE INTERVIEW MASTERY SYSTEM
30 Days to Your Next Job -- Free Guide from Class2Career
By Ignis Spindler, PhD

The interview isn't a test of your expertise. It's a test of your ability
to translate that expertise into business value.

THE 30-DAY SYSTEM

Days 1-7:  Research -- Company fundamentals, market position, competitive landscape.
Days 8-14: Self-Assessment -- Translate every experience into Revenue, Cost, Time, Scale.
Days 15-21: Prep -- 5 questions to ask, STAR method, 60-second metric story.
Days 22-28: Execution -- Anchor every answer in a metric. Signal leadership.
Days 29-30: Follow-Up & Negotiation -- 4-sentence email within 24 hours.

BUSINESS TRANSLATION CHEAT SHEET
"I conducted research" -> "I designed an analysis that produced [finding]"
"I managed a team"    -> "I led [X] people to achieve [outcome]"
"I published papers"  -> "My work was cited [X] times, influencing [industry]"
"I taught students"   -> "I developed curriculum that [measurable outcome]"
"I improved a process"-> "I redesigned [process], reducing [metric] by [X%%]"

Get the complete toolkit: %(site_url)s
(c) 2026 Class2Career | By Ignis Spindler, PhD
"""

def send_lead_magnet(email):
    return _send(
        email,
        "Your Interview Mastery Guide -- Here's What's Next",
        _LEAD_HTML % {'site_url': SITE_URL},
        _LEAD_TEXT % {'site_url': SITE_URL},
    )

# ─── Product Delivery Email ────────────────────────────────────────────────────
_DELIVERY_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0A0E1A;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;color:#FAF7F0;">
<div style="max-width:600px;margin:0 auto;padding:40px 20px;">

  <div style="text-align:center;padding-bottom:28px;border-bottom:1px solid rgba(232,184,75,0.2);">
    <p style="font-size:12px;text-transform:uppercase;letter-spacing:.15em;color:#E8B84B;margin:0 0 10px;">Purchase Confirmed</p>
    <h1 style="font-family:Georgia,serif;font-size:26px;color:#FAF7F0;margin:0 0 8px;">Your Toolkit is Ready</h1>
    <p style="color:#9CA3AF;font-size:14px;margin:0;">Class2Career &mdash; The Business Communication Toolkit</p>
  </div>

  <div style="padding:28px 0 20px;">
    <p style="font-size:16px;line-height:1.7;color:#D4CEC3;margin:0 0 18px;">
      Thank you for your purchase. Everything you need is waiting at the link below &mdash; bookmark it for lifetime access.
    </p>
    <div style="text-align:center;margin:24px 0;">
      <a href="%(access_url)s" style="display:inline-block;background:#E8B84B;color:#0A0E1A;padding:16px 36px;font-weight:bold;font-size:16px;text-decoration:none;border-radius:8px;">Access Your Toolkit &rarr;</a>
    </div>
    <p style="font-size:13px;color:#6B7280;text-align:center;margin:0;">Or copy this link: %(access_url)s</p>
  </div>

  <div style="background:#111827;border-radius:12px;padding:28px;margin-bottom:28px;border:1px solid rgba(232,184,75,0.15);">
    <h2 style="font-family:Georgia,serif;font-size:18px;color:#E8B84B;margin:0 0 16px;">What's Inside</h2>
    <table style="width:100%;border-collapse:collapse;">
      <tr style="border-bottom:1px solid rgba(255,255,255,0.06);">
        <td style="padding:10px 0;color:#E8B84B;font-weight:bold;font-size:13px;width:28px;">01</td>
        <td style="padding:10px 0;color:#FAF7F0;font-size:14px;">The Business Translation Layer</td>
      </tr>
      <tr style="border-bottom:1px solid rgba(255,255,255,0.06);">
        <td style="padding:10px 0;color:#E8B84B;font-weight:bold;font-size:13px;">02</td>
        <td style="padding:10px 0;color:#FAF7F0;font-size:14px;">The 80/20 Operating System</td>
      </tr>
      <tr style="border-bottom:1px solid rgba(255,255,255,0.06);">
        <td style="padding:10px 0;color:#E8B84B;font-weight:bold;font-size:13px;">03</td>
        <td style="padding:10px 0;color:#FAF7F0;font-size:14px;">The Value Dimension</td>
      </tr>
      <tr style="border-bottom:1px solid rgba(255,255,255,0.06);">
        <td style="padding:10px 0;color:#E8B84B;font-weight:bold;font-size:13px;">04</td>
        <td style="padding:10px 0;color:#FAF7F0;font-size:14px;">The Product Dimension</td>
      </tr>
      <tr style="border-bottom:1px solid rgba(255,255,255,0.06);">
        <td style="padding:10px 0;color:#E8B84B;font-weight:bold;font-size:13px;">05</td>
        <td style="padding:10px 0;color:#FAF7F0;font-size:14px;">Personal Growth &amp; The Negotiation Playbook</td>
      </tr>
      <tr>
        <td style="padding:10px 0;color:#E8B84B;font-weight:bold;font-size:13px;">&diams;</td>
        <td style="padding:10px 0;color:#FAF7F0;font-size:14px;">Reflection Journal</td>
      </tr>
    </table>
  </div>

  <div style="padding:0 0 28px;">
    <p style="font-size:14px;line-height:1.7;color:#9CA3AF;margin:0 0 12px;">
      <strong style="color:#E8B84B;">30-Day Money-Back Guarantee:</strong> If this toolkit doesn't help you communicate your value more effectively, reply to this email for a full refund &mdash; no questions asked.
    </p>
    <p style="font-size:14px;line-height:1.7;color:#9CA3AF;margin:0;">Questions? Just reply to this email. I read everything.</p>
  </div>

  <div style="border-top:1px solid rgba(232,184,75,0.15);padding-top:20px;text-align:center;">
    <p style="font-size:13px;color:#6B7280;margin:0 0 4px;">&mdash; Ignis Spindler, PhD</p>
    <p style="font-size:12px;color:#4B5563;margin:0;">&copy; 2026 Class2Career</p>
  </div>
</div>
</body>
</html>"""

_DELIVERY_TEXT = """\
YOUR CLASS2CAREER TOOLKIT IS READY

Access your complete toolkit here:
%(access_url)s

Bookmark this link -- it's yours for lifetime access.

WHAT'S INSIDE:
  01 -- The Business Translation Layer
  02 -- The 80/20 Operating System
  03 -- The Value Dimension
  04 -- The Product Dimension
  05 -- Personal Growth & The Negotiation Playbook
   * -- Reflection Journal

30-Day Money-Back Guarantee: If this doesn't help you communicate your
value more effectively, reply to this email for a full refund -- no
questions asked.

Questions? Just reply to this email.

-- Ignis Spindler, PhD
(c) 2026 Class2Career
"""

def send_delivery_email(email, token):
    access_url = f"{SITE_URL}/access?token={token}"
    return _send(
        email,
        "Your Class2Career Toolkit -- Instant Access Inside",
        _DELIVERY_HTML % {'access_url': access_url},
        _DELIVERY_TEXT % {'access_url': access_url},
    )

# ─── Access Page ───────────────────────────────────────────────────────────────
_ACCESS_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Your Toolkit | Class2Career</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@600;700;800&family=Inter:wght@400;500&display=swap" rel="stylesheet">
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:'Inter',sans-serif;background:#0A0E1A;color:#FAF7F0;min-height:100vh;padding:3rem 1.5rem}
    .wrap{max-width:680px;margin:0 auto}
    .header{text-align:center;padding-bottom:2rem;border-bottom:1px solid rgba(232,184,75,.15);margin-bottom:2.5rem}
    .tag{font-size:.72rem;text-transform:uppercase;letter-spacing:.15em;color:#E8B84B;font-weight:600;margin-bottom:.75rem}
    h1{font-family:'Bricolage Grotesque',sans-serif;font-size:2.2rem;font-weight:800;line-height:1.15;margin-bottom:.5rem}
    .sub{font-size:1rem;color:#9CA3AF}
    .books{display:flex;flex-direction:column;gap:1rem;margin-bottom:2.5rem}
    .book{display:flex;align-items:center;gap:1.25rem;background:#111827;border:1px solid rgba(232,184,75,.12);border-radius:12px;padding:1.25rem 1.5rem;text-decoration:none;color:inherit;transition:border-color .2s,transform .2s}
    .book:hover{border-color:rgba(232,184,75,.4);transform:translateY(-2px)}
    .num{font-family:'Bricolage Grotesque',sans-serif;font-size:1.5rem;font-weight:800;color:#E8B84B;min-width:2.5rem;text-align:center}
    .info{flex:1}
    .info strong{display:block;font-size:1rem;margin-bottom:.2rem}
    .info span{font-size:.85rem;color:#9CA3AF}
    .arrow{color:#E8B84B;font-size:1.2rem;opacity:.6}
    .guarantee{background:#111827;border:1px solid rgba(232,184,75,.12);border-radius:12px;padding:1.5rem;text-align:center}
    .guarantee h3{font-size:1rem;margin-bottom:.5rem;color:#E8B84B}
    .guarantee p{font-size:.88rem;color:#9CA3AF;line-height:1.6}
    .guarantee a{color:#E8B84B}
    .footer{text-align:center;margin-top:2.5rem;font-size:.8rem;color:#4B5563}
    @media(max-width:500px){h1{font-size:1.7rem}.book{flex-direction:column;align-items:flex-start}.arrow{display:none}}
  </style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div class="tag">Purchase Confirmed</div>
    <h1>Your Toolkit is Ready</h1>
    <p class="sub">Class2Career &mdash; The Business Communication Toolkit</p>
  </div>

  <div class="books">
    <a class="book" href="/downloads/workbook-01-business-foundation.html" target="_blank">
      <div class="num">01</div>
      <div class="info">
        <strong>The Business Translation Layer</strong>
        <span>Business as an organism &mdash; how to think, see, and speak like an insider</span>
      </div>
      <div class="arrow">&#8594;</div>
    </a>
    <a class="book" href="/downloads/workbook-02-sales-dimension.html" target="_blank">
      <div class="num">02</div>
      <div class="info">
        <strong>The 80/20 Operating System</strong>
        <span>Sales, revenue metrics, and how decisions actually get made</span>
      </div>
      <div class="arrow">&#8594;</div>
    </a>
    <a class="book" href="/downloads/workbook-03-value-dimension.html" target="_blank">
      <div class="num">03</div>
      <div class="info">
        <strong>The Value Dimension</strong>
        <span>Communicating ROI, efficiency, and impact &mdash; in any room</span>
      </div>
      <div class="arrow">&#8594;</div>
    </a>
    <a class="book" href="/downloads/workbook-04-product-dimension.html" target="_blank">
      <div class="num">04</div>
      <div class="info">
        <strong>The Product Dimension</strong>
        <span>Product thinking, storytelling frameworks, and persuasion</span>
      </div>
      <div class="arrow">&#8594;</div>
    </a>
    <a class="book" href="/downloads/workbook-05-personal-growth.html" target="_blank">
      <div class="num">05</div>
      <div class="info">
        <strong>Personal Growth &amp; The Negotiation Playbook</strong>
        <span>Salary, scope, and career moves &mdash; negotiated with confidence</span>
      </div>
      <div class="arrow">&#8594;</div>
    </a>
    <a class="book" href="/downloads/reflection-journal.html" target="_blank">
      <div class="num">&#9830;</div>
      <div class="info">
        <strong>Reflection Journal</strong>
        <span>Exercises, worksheets, and action plans for all five workbooks</span>
      </div>
      <div class="arrow">&#8594;</div>
    </a>
  </div>

  <div class="guarantee">
    <h3>&#127942; 30-Day Money-Back Guarantee</h3>
    <p>If this toolkit doesn't help you communicate your value more effectively, email <a href="mailto:ignis@biztranslation.com">ignis@biztranslation.com</a> for a full refund &mdash; no questions asked.</p>
  </div>

  <div class="footer">
    <p>&copy; 2026 Class2Career &nbsp;&middot;&nbsp; By Ignis Spindler, PhD</p>
  </div>
</div>
</body>
</html>"""

_ACCESS_DENIED = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Access Denied | Class2Career</title>
  <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{font-family:sans-serif;background:#0A0E1A;color:#FAF7F0;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:2rem;text-align:center}}
    .wrap{{max-width:440px}}
    h1{{font-size:1.6rem;margin-bottom:1rem;color:#E8B84B}}
    p{{color:#9CA3AF;line-height:1.7;margin-bottom:1.25rem}}
    a{{color:#E8B84B}}
  </style>
</head>
<body>
<div class="wrap">
  <h1>{title}</h1>
  <p>{msg}</p>
  <p>If you believe this is an error, please email <a href="mailto:ignis@biztranslation.com">ignis@biztranslation.com</a> with your purchase receipt.</p>
</div>
</body>
</html>"""

# ─── Routes ────────────────────────────────────────────────────────────────────
@app.route("/subscribe", methods=["POST"])
def subscribe():
    email = request.form.get("email", "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"error": "Valid email required"}), 400

    save_lead(
        email,
        lead_magnet=request.form.get("lead_magnet", ""),
        source_url=request.referrer or "",
        utm_source=request.form.get("utm_source", ""),
        utm_medium=request.form.get("utm_medium", ""),
        utm_campaign=request.form.get("utm_campaign", ""),
    )
    email_sent = send_lead_magnet(email)
    print(f"[Subscribe] {email} -> email_sent={email_sent}")

    return jsonify({
        "success": True,
        "message": "Check your inbox for the Interview Mastery Guide!",
        "email_sent": email_sent,
    })


@app.route("/webhook/stripe", methods=["POST"])
def webhook_stripe():
    payload = request.get_data()
    sig     = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe_lib.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        print("[Stripe] Invalid payload")
        abort(400)
    except stripe_lib.error.SignatureVerificationError:
        print("[Stripe] Invalid signature")
        abort(400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        email = (
            session.get("customer_details", {}).get("email")
            or session.get("customer_email", "")
        )
        if email:
            token = secrets.token_urlsafe(32)
            save_purchase(email, session["id"], token)
            save_lead(email, utm_source="stripe_purchase", lead_magnet="purchase")
            sent = send_delivery_email(email, token)
            print(f"[Purchase] {email} -> delivery_sent={sent}")

    return jsonify({"received": True}), 200


@app.route("/access", methods=["GET"])
def access():
    token = request.args.get("token", "").strip()
    if not token:
        resp = make_response(
            _ACCESS_DENIED.format(
                title="No Access Token",
                msg="This link is missing an access token. Please use the link from your purchase confirmation email."
            ),
            403
        )
        resp.headers["Content-Type"] = "text/html"
        return resp

    data = r_get(f"token:{token}")
    if not data or not data.get("valid"):
        resp = make_response(
            _ACCESS_DENIED.format(
                title="Invalid Token",
                msg="This access link is invalid or has expired."
            ),
            403
        )
        resp.headers["Content-Type"] = "text/html"
        return resp

    resp = make_response(_ACCESS_PAGE, 200)
    resp.headers["Content-Type"] = "text/html"
    return resp


# Vercel WSGI entry point
try:
    from vercel.wsgi import Vercel
    app = Vercel(app)
except ImportError:
    pass
