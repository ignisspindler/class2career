"""
api/index.py — Class2Career Backend
Routes: /subscribe, /webhook/stripe, /access, /download, /cron/send-sequence, /stats
Storage: Upstash Redis
Email:   SendGrid
Payments: Stripe Webhooks
"""
import os
import json
import time
import secrets
import urllib.request
import stripe as stripe_lib
from flask import Flask, request, jsonify, abort, make_response, send_file
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

app = Flask(__name__)

# ─── Config ────────────────────────────────────────────────────────────────────
UPSTASH_URL           = os.environ.get('UPSTASH_REDIS_REST_URL', '')
UPSTASH_TOKEN         = os.environ.get('UPSTASH_REDIS_REST_TOKEN', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
SENDGRID_KEY          = os.environ.get('SENDGRID_API_KEY', '')
FROM_EMAIL            = 'ignis@biztranslation.com'
ADMIN_EMAIL           = 'hello@eugenegeis.com'
CRON_SECRET           = os.environ.get('CRON_SECRET', '')

stripe_lib.api_key = os.environ.get('STRIPE_SECRET_KEY', '')

_REPO_ROOT      = os.path.join(os.path.dirname(__file__), '..')
_LEAD_PDF_DIR   = os.path.join(_REPO_ROOT, 'lead_magnets')
_WORKBOOK_DIR   = os.path.join(_REPO_ROOT, 'downloads')

# ─── Cohort Config ─────────────────────────────────────────────────────────────
COHORTS = {
    'biztranslation': {
        'site':     'https://biztranslation.com',
        'brand':    'BizTranslation',
        'pdf':      'interview-mastery-biztranslation.pdf',
        'audience': 'professionals making a career shift',
        'pitch':    'turn your expertise into the language business runs on',
    },
    'class2careers': {
        'site':     'https://class2careers.com',
        'brand':    'Class2Career',
        'pdf':      'interview-mastery-class2careers.pdf',
        'audience': 'recent graduates entering the workforce',
        'pitch':    'negotiate for more than the first number they give you',
    },
    'phd2pro': {
        'site':     'https://phd2pro.com',
        'brand':    'PhD2Pro',
        'pdf':      'interview-mastery-phd2pro.pdf',
        'audience': 'academics and researchers moving to industry',
        'pitch':    'translate years of research into the language industry pays for',
    },
    'transition2corporate': {
        'site':     'https://transition2corporate.com',
        'brand':    'Transition2Corporate',
        'pdf':      'interview-mastery-transition2corporate.pdf',
        'audience': 'public sector professionals entering the private sector',
        'pitch':    'reframe your government and nonprofit experience as business assets',
    },
}

WORKBOOK_FILES = {
    'wb01':    ('workbook-01-business-foundation.html',      'Workbook 01 — The Business Translation Layer'),
    'wb02':    ('workbook-02-sales-dimension.html',          'Workbook 02 — The 80/20 Operating System'),
    'wb03':    ('workbook-03-value-dimension.html',          'Workbook 03 — The Value Dimension'),
    'wb04':    ('workbook-04-product-dimension.html',        'Workbook 04 — The Product Dimension'),
    'wb05':    ('workbook-05-personal-growth.html',          'Workbook 05 — Personal Growth & The Negotiation Playbook'),
    'journal': ('reflection-journal.html',                   'Reflection Journal'),
}

# Days after subscribe when each sequence email is due (seq 1 = 0 = immediate)
SEQ_DAYS = {1: 0, 2: 7, 3: 14, 4: 21, 5: 50, 6: 80}

def get_cohort(key):
    return COHORTS.get(key) or COHORTS['class2careers']


# ─── Upstash Redis ─────────────────────────────────────────────────────────────
def _redis(*cmd):
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
    if ex: cmd += ['EX', str(ex)]
    return _redis(*cmd)

def r_get(key):
    raw = _redis('GET', key)
    if not raw: return None
    try: return json.loads(raw)
    except (TypeError, json.JSONDecodeError): return raw

def r_sadd(key, member):
    return _redis('SADD', key, member)

def r_scard(key):
    result = _redis('SCARD', key)
    return int(result) if result is not None else 0

def r_smembers(key):
    result = _redis('SMEMBERS', key)
    return list(result) if result else []

def r_sismember(key, member):
    result = _redis('SISMEMBER', key, member)
    return bool(result)


# ─── Lead & Purchase Storage ────────────────────────────────────────────────────
def save_lead(email, cohort='', **meta):
    key = f'lead:{email}'
    if r_get(key):
        return False
    r_set(key, {'email': email, 'cohort': cohort, **meta})
    r_set(f'seq:subscribed_at:{email}', int(time.time()))
    r_sadd('leads:all', email)
    if cohort:
        r_sadd(f'leads:cohort:{cohort}', email)
    return True

def save_purchase(email, session_id, token, cohort=''):
    r_set(f'purchase:{email}', {
        'email': email, 'session_id': session_id,
        'token': token, 'cohort': cohort,
    })
    r_set(f'token:{token}', {'email': email, 'valid': True})
    r_sadd('purchases:all', email)
    if cohort:
        r_sadd(f'purchases:cohort:{cohort}', email)

def has_purchased(email):
    return bool(r_get(f'purchase:{email}'))

def seq_already_sent(email, seq_num):
    return r_sismember(f'seq:sent:{email}', str(seq_num))

def seq_mark_sent(email, seq_num):
    r_sadd(f'seq:sent:{email}', str(seq_num))
    _redis('INCR', f'seq:total:{seq_num}')  # global counter for dashboard


# ─── Email Infrastructure ───────────────────────────────────────────────────────
def _alert_quota():
    try:
        sg = SendGridAPIClient(SENDGRID_KEY)
        msg = Mail(Email(FROM_EMAIL), To(ADMIN_EMAIL),
                   'ACTION REQUIRED: SendGrid send quota reached')
        msg.add_content(Content('text/plain',
            'SendGrid has hit its monthly quota. Upgrade at app.sendgrid.com '
            'under Settings > Plan & Billing to resume email delivery.'
        ))
        sg.send(msg)
    except Exception as ex:
        print(f"[Alert] Could not send quota alert: {ex}")

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
        err = str(e)
        print(f"[SendGrid error] {type(e).__name__}: {err}")
        if any(x in err for x in ['quota', '429', 'limit exceeded', 'Forbidden']):
            _alert_quota()
        return False


# ─── Email HTML/Text Helpers ────────────────────────────────────────────────────
def _wrap(inner, c):
    site_short = c['site'].replace('https://', '')
    return (
        f'<!DOCTYPE html><html><head><meta charset="UTF-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        f'<body style="margin:0;padding:0;background:#0A0E1A;'
        f'font-family:\'Helvetica Neue\',Helvetica,Arial,sans-serif;color:#FAF7F0;">'
        f'<div style="max-width:600px;margin:0 auto;padding:40px 20px;">'
        f'{inner}'
        f'<div style="border-top:1px solid rgba(232,184,75,0.15);padding-top:20px;'
        f'margin-top:32px;text-align:center;">'
        f'<p style="font-size:12px;color:#6B7280;margin:0 0 3px;">'
        f'Ignis Spindler, PhD &nbsp;&middot;&nbsp; {c["brand"]}</p>'
        f'<p style="font-size:11px;color:#4B5563;margin:0;">'
        f'You received this because you downloaded the Interview Mastery Guide at '
        f'<a href="{c["site"]}" style="color:#E8B84B;text-decoration:none;">{site_short}</a>.</p>'
        f'</div>'
        f'</div></body></html>'
    )

def _btn(url, label):
    return (
        f'<div style="text-align:center;margin:28px 0;">'
        f'<a href="{url}" style="display:inline-block;background:#E8B84B;color:#0A0E1A;'
        f'padding:14px 32px;font-weight:bold;font-size:15px;text-decoration:none;'
        f'border-radius:8px;">{label}</a></div>'
    )

def _p(text, color='#D4CEC3'):
    return f'<p style="font-size:15px;line-height:1.75;color:{color};margin:0 0 18px;">{text}</p>'

def _h1(text):
    return (
        f'<div style="padding-bottom:24px;border-bottom:1px solid rgba(232,184,75,0.2);'
        f'margin-bottom:28px;text-align:center;">'
        f'<h1 style="font-family:Georgia,serif;font-size:24px;color:#E8B84B;margin:0;">'
        f'{text}</h1></div>'
    )

def _footer_txt(c):
    site_short = c['site'].replace('https://', '')
    return (
        f"\n--\nIgnis Spindler, PhD | {c['brand']} | {site_short}\n"
        f"You received this because you downloaded the Interview Mastery Guide."
    )


# ─── Email 1: Immediate — Welcome + Secure PDF Download ────────────────────────
def _email1_opener(c):
    openers = {
        'class2careers': (
            "You just picked up the Interview Mastery Guide. Good call. "
            "Most graduates walk into interviews with strong credentials and weak framing. "
            "They talk about what they studied. The interviewer is listening for what they can do for the business. "
            "This guide closes that gap."
        ),
        'phd2pro': (
            "You just picked up the Interview Mastery Guide. "
            "You have more expertise than most people in that interview room. "
            "The problem is that interviewers can't see it yet, because academic language and business language "
            "are not the same thing. This guide gives you the translation layer."
        ),
        'transition2corporate': (
            "You just picked up the Interview Mastery Guide. "
            "You have managed real programs, real budgets, and real stakeholders. "
            "Private-sector interviewers can't recognize that until you speak their language. "
            "This guide teaches you how to reframe your experience so it lands."
        ),
        'biztranslation': (
            "You just picked up the Interview Mastery Guide. "
            "Your background has real value. The question is whether you can communicate that value "
            "in the language that gets people hired and paid. "
            "This guide gives you the framework to do exactly that."
        ),
    }
    return openers.get(c.get('brand', '').lower().replace(' ', ''), openers['biztranslation'])

_EMAIL1_INNER = """\
{h1}
{p_open}
{p_guide}
{btn_dl}
{p_earn}
{p_every}
{p_cta}
{btn_toolkit}
"""

def email1(c, download_url):
    opener = _email1_opener(c)
    inner = (
        _h1("Your Interview Mastery Guide") +
        _p(opener) +
        _p("Your guide is ready. Read every page. Bring a pen.") +
        _btn(download_url, "Download the Interview Mastery Guide") +
        _p(
            f"Here is something most {c['audience']} underestimate: "
            "you are worth more than the first number any employer quotes you. "
            "The people who capture that extra value aren't more qualified. "
            "They have learned to frame their experience in terms of business outcomes, "
            "not credentials. That is what this guide teaches.",
            '#D4CEC3'
        ) +
        _p(
            "<strong style=\"color:#E8B84B;\">Read every single word.</strong> "
            "Not just the frameworks. The examples. The phrasing. The specific language. "
            "The difference between a callback and silence is often one sentence.",
            '#D4CEC3'
        ) +
        _p(
            f"When you're ready to go deeper, the full {c['brand']} workbook series covers "
            "business fundamentals, value communication, the sales mindset, and a complete "
            "negotiation playbook. Five workbooks, one price.",
            '#9CA3AF'
        ) +
        _btn(c['site'], f"Get the Full Toolkit")
    )
    html = _wrap(inner, c)
    txt = (
        f"YOUR INTERVIEW MASTERY GUIDE\n\n"
        f"{opener}\n\n"
        f"Your download link:\n{download_url}\n\n"
        f"Read every single word. Bring a pen.\n\n"
        f"You are worth more than the first number any employer quotes you. "
        f"The people who capture that extra value aren't more qualified -- "
        f"they have learned to frame their experience in terms of business outcomes.\n\n"
        f"When you're ready to go deeper:\n{c['site']}"
        + _footer_txt(c)
    )
    return "Your Interview Mastery Guide", html, txt


# ─── Email 2: Day 7 — The Translation Gap ──────────────────────────────────────
def email2(c):
    inner = (
        _h1("The gap is not your credentials") +
        _p(
            "A mechanical engineer had spent a decade in manufacturing. "
            "She had real numbers: reduced defect rates by 31%, managed three cross-functional teams, "
            "shipped two products to market. She was applying to product management roles at tech companies."
        ) +
        _p(
            "In every interview, she talked about designing robust mechanical systems and iterating on test fixtures. "
            "Nobody called back. She assumed she wasn't qualified enough."
        ) +
        _p(
            "Then she changed one thing. She started opening every answer with the business outcome. "
            "'I led the team that cut production defects by 31%, which translated to $2.4M in savings over 18 months.' "
            "Same resume. Same experience. Different language. "
            "Three job offers arrived in the next six weeks."
        ) +
        _p(
            "The gap isn't your credentials. It's the translation. "
            "Every answer you give in an interview should lead with an outcome the business cares about "
            "and follow with the action that produced it. Never the other way around.",
            '#9CA3AF'
        ) +
        _p(
            "Before your next interview, take three of your biggest experiences and rewrite them "
            "in this format: <em style=\"color:#E8B84B;\">[Outcome in business terms] because I [action].</em> "
            "That rewrite is the practice that separates candidates who get callbacks from those who don't.",
            '#9CA3AF'
        ) +
        _btn(c['site'], f"Get the Full {c['brand']} Toolkit")
    )
    html = _wrap(inner, c)
    txt = (
        "THE GAP IS NOT YOUR CREDENTIALS\n\n"
        "A mechanical engineer had spent a decade in manufacturing. "
        "She had real numbers: reduced defect rates by 31%, managed three cross-functional teams, "
        "shipped two products to market. She was applying to product management roles at tech companies.\n\n"
        "In every interview, she talked about designing robust mechanical systems and iterating on test fixtures. "
        "Nobody called back. She assumed she wasn't qualified enough.\n\n"
        "Then she changed one thing. She started opening every answer with the business outcome. "
        "'I led the team that cut production defects by 31%, which translated to $2.4M in savings over 18 months.' "
        "Same resume. Same experience. Different language. "
        "Three job offers in six weeks.\n\n"
        "The gap isn't your credentials. It's the translation. "
        "Every answer should lead with an outcome the business cares about, "
        "then follow with the action that produced it. Never the other way around.\n\n"
        "Practice: take three of your biggest experiences and rewrite them as "
        "[Outcome in business terms] because I [action].\n\n"
        f"The full toolkit: {c['site']}"
        + _footer_txt(c)
    )
    subject = "The one rewrite that changes your callback rate"
    return subject, html, txt


# ─── Email 3: Day 14 — The Value Pitch ─────────────────────────────────────────
def email3(c):
    inner = (
        _h1("Clinical knowledge vs. a revenue pitch") +
        _p(
            "A nurse practitioner was interviewing for a clinical sales role at a medical device company. "
            "She knew the product cold. She had used it hundreds of times, understood the complications, "
            "could walk through the procedure in her sleep."
        ) +
        _p(
            "In every interview, she led with clinical knowledge. "
            "'I've placed over 200 of these catheters. I understand the failure modes.' "
            "The feedback she kept getting: strong clinical background, not sure about fit for sales."
        ) +
        _p(
            "The hiring manager told her later what she'd been missing. "
            "'We weren't hiring a clinician. We needed someone who could sell to clinicians.' "
            "She adjusted her opening for the next interview: "
            "'I've placed over 200 of these catheters and I know exactly where they fail. "
            "Give me that account list and I will cut your return rate by half within a quarter.' "
            "That is not clinical knowledge. That is a revenue pitch. She got the job."
        ) +
        _p(
            "Your expertise has value. The question is whether you are presenting it "
            "as a qualification or as a business outcome. Qualifications get you into the room. "
            "Business outcomes get you an offer.",
            '#9CA3AF'
        ) +
        _p(
            "For your next interview, find one specific piece of expertise you have "
            "and turn it into a sentence that starts with a revenue, cost, or efficiency claim. "
            "That is your opening.",
            '#9CA3AF'
        ) +
        _btn(c['site'], f"Get the Full {c['brand']} Toolkit")
    )
    html = _wrap(inner, c)
    txt = (
        "CLINICAL KNOWLEDGE VS. A REVENUE PITCH\n\n"
        "A nurse practitioner was interviewing for a clinical sales role at a medical device company. "
        "She knew the product cold -- 200+ placements, understood the failure modes cold.\n\n"
        "She kept leading with clinical credentials. The feedback: strong clinical background, "
        "not sure about fit for sales.\n\n"
        "What she was missing: the hiring manager wasn't hiring a clinician. "
        "They needed someone who could sell to clinicians. "
        "She adjusted: 'I've placed over 200 of these catheters and I know exactly where they fail. "
        "Give me that account list and I'll cut your return rate by half within a quarter.' "
        "That's a revenue pitch. She got the job.\n\n"
        "Your expertise has value. Present it as a business outcome, not a qualification. "
        "Qualifications get you into the room. Outcomes get you an offer.\n\n"
        "Find one piece of expertise and turn it into a sentence that starts "
        "with a revenue, cost, or efficiency claim. That is your opening.\n\n"
        f"The full toolkit: {c['site']}"
        + _footer_txt(c)
    )
    subject = "The difference between a qualification and a revenue pitch"
    return subject, html, txt


# ─── Email 4: Day 21 — The Four-Second Pause ───────────────────────────────────
def email4(c):
    inner = (
        _h1("Four seconds of silence, worth $13,000") +
        _p(
            "A materials science PhD got an offer from a Fortune 500 company: $92,000. "
            "His research had saved them an estimated $4M in R&D costs. "
            "He accepted immediately. He had been worried they wouldn't want him at all."
        ) +
        _p(
            "His colleague got an equivalent offer for the same role, same qualifications. "
            "She had done her homework: market rate was $104-110K for that specialty in that region. "
            "She said: 'I'm genuinely excited about this. Based on the scope of the work and "
            "what I've found in market data, I was expecting something closer to $108K. "
            "Is there room to get there?'"
        ) +
        _p(
            "Four seconds of silence. Then: 'Let me talk to the team.' "
            "Final offer: $105,000. Nobody called her bluff. Nobody rescinded the offer. "
            "She did not lose the job for asking. The researcher who said yes immediately "
            "left $13,000 on the table every single year going forward."
        ) +
        _p(
            "Nobody ever lost a job offer for asking, with a number they can defend. "
            "The people who walk away with better offers are not more qualified or more confident. "
            "They simply did not say yes to the first number.",
            '#9CA3AF'
        ) +
        _p(
            "Before your next offer conversation, look up market rate for that exact role "
            "in that region, build your number, and write out the one sentence you'll say. "
            "You don't need to be aggressive. You need to be specific.",
            '#9CA3AF'
        ) +
        _btn(c['site'], f"Get the Full {c['brand']} Toolkit")
    )
    html = _wrap(inner, c)
    txt = (
        "FOUR SECONDS OF SILENCE, WORTH $13,000\n\n"
        "A materials science PhD got an offer for $92,000. "
        "His research had saved the company an estimated $4M in R&D costs. He said yes immediately.\n\n"
        "His colleague got the same offer. She had done her homework: market rate was $104-110K. "
        "She said: 'I'm excited. Based on the scope of the work and my market research, "
        "I was expecting closer to $108K. Is there room to get there?'\n\n"
        "Four seconds of silence. Then: 'Let me talk to the team.'\n"
        "Final offer: $105,000.\n\n"
        "Nobody ever lost a job offer for asking with a number they can defend. "
        "The difference is not confidence -- it's preparation. "
        "Look up market rate, build your number, write one sentence, and don't say yes to the first offer.\n\n"
        f"The full toolkit: {c['site']}"
        + _footer_txt(c)
    )
    subject = "Nobody ever lost a job offer for asking"
    return subject, html, txt


# ─── Email 5: Day 50 — The Meritocracy Myth + 30% Off ─────────────────────────
def email5(c):
    discount_url = f"{c['site']}/?coupon=TOOLKIT30"
    inner = (
        _h1("The most damaging idea in professional life") +
        _p(
            "Most people believe the best work gets rewarded. It does not. "
            "The best-communicated work gets rewarded."
        ) +
        _p(
            "Two people can run the same project, produce the same results, "
            "and walk into the same performance review. "
            "The one who frames their work in terms of revenue impact, cost savings, "
            "and executive priorities gets the promotion, the raise, the expanded scope. "
            "The other gets a polite thank-you and a flat salary."
        ) +
        _p(
            "This is not a complaint about how unfair the world is. "
            "It is a description of how organizations actually work, "
            "and it means there is a specific skill that determines who gets ahead: "
            "the ability to communicate what you do in the language that decision-makers use to think. "
            "Workbook 5 of the toolkit teaches you exactly that, including how to build a full "
            "negotiation playbook before you ever sit down at the table."
        ) +
        _p(
            f"<strong style=\"color:#E8B84B;\">For the next 30 days, the complete {c['brand']} "
            "toolkit is 30% off with code TOOLKIT30.</strong> "
            "That's five workbooks covering business fundamentals, sales thinking, "
            "value communication, product strategy, and personal growth.",
            '#D4CEC3'
        ) +
        _btn(discount_url, "Get 30% Off — Code TOOLKIT30") +
        _p("This discount expires in 30 days.", '#6B7280')
    )
    html = _wrap(inner, c)
    txt = (
        "THE MOST DAMAGING IDEA IN PROFESSIONAL LIFE\n\n"
        "Most people believe the best work gets rewarded. It does not. "
        "The best-communicated work gets rewarded.\n\n"
        "Two people can run the same project and walk into the same performance review. "
        "The one who frames their work in terms of revenue impact and cost savings gets the promotion. "
        "The other gets a flat salary.\n\n"
        "This is not a complaint. It is a description of how organizations work -- "
        "which means there is a learnable skill that determines who gets ahead. "
        "Workbook 5 of the toolkit teaches you exactly that.\n\n"
        f"For the next 30 days, the complete {c['brand']} toolkit is 30% off with code TOOLKIT30.\n"
        f"Get it here: {discount_url}\n\n"
        "This discount expires in 30 days."
        + _footer_txt(c)
    )
    subject = "The skill that determines who gets promoted (and a discount)"
    return subject, html, txt


# ─── Email 6: Day 80 — Leverage Inventory + Last Chance ────────────────────────
def email6(c):
    discount_url = f"{c['site']}/?coupon=TOOLKIT30"
    inner = (
        _h1("Most people show up with one number and nothing else") +
        _p(
            "Before any salary negotiation, the people who close at higher numbers do something "
            "most candidates skip entirely: they build a leverage inventory."
        ) +
        _p(
            "A leverage inventory is a written list of every piece of negotiating power you have. "
            "Market rate for your exact role and region. "
            "Specialized skills that would cost $40-60K to replace or train. "
            "Documented outcomes from your past work, in business terms. "
            "Any competing interest or competing offer, real or plausible. "
            "The cost to the organization of a long vacancy in that role. "
            "Your leverage exists. Most people simply never name it before they walk in."
        ) +
        _p(
            "The person who shows up with a six-item leverage inventory negotiates from a different position "
            "than the person who shows up with 'I've been here three years' or 'I really need this job.' "
            "Workbook 5 walks through building your full inventory and how to use each item. "
            "It is one of the most high-return things you can spend two hours on."
        ) +
        _p(
            f"<strong style=\"color:#E8B84B;\">Last chance: 30% off the complete {c['brand']} "
            "toolkit with code TOOLKIT30.</strong> "
            "This price expires in 7 days. After that it goes back to full price.",
            '#D4CEC3'
        ) +
        _btn(discount_url, "Last Chance: 30% Off with TOOLKIT30") +
        _p("Five workbooks. One price. Yours to keep.", '#6B7280')
    )
    html = _wrap(inner, c)
    txt = (
        "MOST PEOPLE SHOW UP WITH ONE NUMBER AND NOTHING ELSE\n\n"
        "Before any salary negotiation, the people who close at higher numbers build a leverage inventory: "
        "a written list of every piece of negotiating power they have.\n\n"
        "Market rate for the exact role and region. Specialized skills that cost $40-60K to replace. "
        "Documented business outcomes. Any competing interest. The cost of a long vacancy. "
        "Your leverage exists. Most people just never name it.\n\n"
        "The person with a six-item leverage inventory negotiates from a different position "
        "than the person who shows up with 'I've been here three years.' "
        "Workbook 5 walks through building your full inventory and how to use it.\n\n"
        f"Last chance: 30% off the complete toolkit with code TOOLKIT30.\n"
        f"Expires in 7 days: {discount_url}\n\n"
        "Five workbooks. One price. Yours to keep."
        + _footer_txt(c)
    )
    subject = "Last chance: 30% off (and a negotiation framework worth reading)"
    return subject, html, txt


# ─── Purchase Thank-You ─────────────────────────────────────────────────────────
def email_purchase(c, access_url):
    inner = (
        _h1("You're in. Here's your toolkit.") +
        _p("Thank you for purchasing. Everything is ready at the link below. Bookmark it.") +
        _btn(access_url, "Access Your Toolkit") +
        f'<p style="font-size:13px;color:#6B7280;text-align:center;margin:-12px 0 24px;">'
        f'Or copy: {access_url}</p>' +
        '<div style="background:#111827;border-radius:10px;padding:24px;margin:0 0 24px;'
        'border:1px solid rgba(232,184,75,0.12);">'
        '<p style="font-size:13px;text-transform:uppercase;letter-spacing:.1em;'
        'color:#E8B84B;margin:0 0 14px;font-weight:600;">What\'s inside</p>'
        '<table style="width:100%;border-collapse:collapse;">' +
        ''.join(
            f'<tr style="border-bottom:1px solid rgba(255,255,255,0.06);">'
            f'<td style="padding:9px 0;color:#E8B84B;font-weight:bold;font-size:13px;width:28px;">{num}</td>'
            f'<td style="padding:9px 0;color:#FAF7F0;font-size:14px;">{title}</td></tr>'
            for num, title in [
                ('01', 'The Business Translation Layer'),
                ('02', 'The 80/20 Operating System'),
                ('03', 'The Value Dimension'),
                ('04', 'The Product Dimension'),
                ('05', 'Personal Growth &amp; The Negotiation Playbook'),
                ('&diams;', 'Reflection Journal'),
            ]
        ) +
        '</table></div>' +
        _p(
            '<strong style="color:#E8B84B;">30-day guarantee:</strong> '
            'If this does not help you communicate your value more effectively, '
            'reply to this email for a full refund. No forms, no questions.',
            '#9CA3AF'
        )
    )
    html = _wrap(inner, c)
    txt = (
        "YOU'RE IN. HERE'S YOUR TOOLKIT.\n\n"
        f"Access your complete toolkit: {access_url}\n\n"
        "Bookmark that link.\n\n"
        "WHAT'S INSIDE:\n"
        "  01 -- The Business Translation Layer\n"
        "  02 -- The 80/20 Operating System\n"
        "  03 -- The Value Dimension\n"
        "  04 -- The Product Dimension\n"
        "  05 -- Personal Growth & The Negotiation Playbook\n"
        "   * -- Reflection Journal\n\n"
        "30-day guarantee: if this doesn't help you communicate your value more effectively, "
        "reply for a full refund. No forms, no questions."
        + _footer_txt(c)
    )
    brand = c['brand']
    return f"Your {brand} toolkit is ready", html, txt


# ─── Sequence Dispatch ──────────────────────────────────────────────────────────
def send_seq_email(email, seq_num, cohort_key, **kwargs):
    """Send sequence email seq_num to email. Returns True on success."""
    c = get_cohort(cohort_key)
    if seq_num == 1:
        download_url = kwargs.get('download_url', c['site'])
        subject, html, txt = email1(c, download_url)
    elif seq_num == 2:
        subject, html, txt = email2(c)
    elif seq_num == 3:
        subject, html, txt = email3(c)
    elif seq_num == 4:
        subject, html, txt = email4(c)
    elif seq_num == 5:
        subject, html, txt = email5(c)
    elif seq_num == 6:
        subject, html, txt = email6(c)
    else:
        return False
    ok = _send(email, subject, html, txt)
    if ok:
        seq_mark_sent(email, seq_num)
    return ok


# ─── Access Page ───────────────────────────────────────────────────────────────
def _access_page_html(purchase_token):
    def _book_link(num, key, title, subtitle):
        url = f"/download?token={purchase_token}&file={key}"
        return (
            f'<a class="book" href="{url}" target="_blank">'
            f'<div class="num">{num}</div>'
            f'<div class="info"><strong>{title}</strong><span>{subtitle}</span></div>'
            f'<div class="arrow">&#8594;</div></a>'
        )

    books = (
        _book_link('01', 'wb01', 'The Business Translation Layer',
                   'Business as an organism: how to think, see, and speak like an insider') +
        _book_link('02', 'wb02', 'The 80/20 Operating System',
                   'Sales, revenue metrics, and how decisions actually get made') +
        _book_link('03', 'wb03', 'The Value Dimension',
                   'Communicating ROI, efficiency, and impact in any room') +
        _book_link('04', 'wb04', 'The Product Dimension',
                   'Product thinking, storytelling frameworks, and persuasion') +
        _book_link('05', 'wb05', 'Personal Growth & The Negotiation Playbook',
                   'Salary, scope, and career moves negotiated with confidence') +
        _book_link('&diams;', 'journal', 'Reflection Journal',
                   'Exercises, worksheets, and action plans for all five workbooks')
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Your Toolkit | Class2Career</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@600;700;800&family=Inter:wght@400;500&display=swap" rel="stylesheet">
  <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{font-family:'Inter',sans-serif;background:#0A0E1A;color:#FAF7F0;min-height:100vh;padding:3rem 1.5rem}}
    .wrap{{max-width:680px;margin:0 auto}}
    .header{{text-align:center;padding-bottom:2rem;border-bottom:1px solid rgba(232,184,75,.15);margin-bottom:2.5rem}}
    .tag{{font-size:.72rem;text-transform:uppercase;letter-spacing:.15em;color:#E8B84B;font-weight:600;margin-bottom:.75rem}}
    h1{{font-family:'Bricolage Grotesque',sans-serif;font-size:2.2rem;font-weight:800;line-height:1.15;margin-bottom:.5rem}}
    .sub{{font-size:1rem;color:#9CA3AF}}
    .books{{display:flex;flex-direction:column;gap:1rem;margin-bottom:2.5rem}}
    .book{{display:flex;align-items:center;gap:1.25rem;background:#111827;border:1px solid rgba(232,184,75,.12);border-radius:12px;padding:1.25rem 1.5rem;text-decoration:none;color:inherit;transition:border-color .2s,transform .2s}}
    .book:hover{{border-color:rgba(232,184,75,.4);transform:translateY(-2px)}}
    .num{{font-family:'Bricolage Grotesque',sans-serif;font-size:1.5rem;font-weight:800;color:#E8B84B;min-width:2.5rem;text-align:center}}
    .info{{flex:1}}
    .info strong{{display:block;font-size:1rem;margin-bottom:.2rem}}
    .info span{{font-size:.85rem;color:#9CA3AF}}
    .arrow{{color:#E8B84B;font-size:1.2rem;opacity:.6}}
    .guarantee{{background:#111827;border:1px solid rgba(232,184,75,.12);border-radius:12px;padding:1.5rem;text-align:center}}
    .guarantee h3{{font-size:1rem;margin-bottom:.5rem;color:#E8B84B}}
    .guarantee p{{font-size:.88rem;color:#9CA3AF;line-height:1.6}}
    .guarantee a{{color:#E8B84B}}
    .footer{{text-align:center;margin-top:2.5rem;font-size:.8rem;color:#4B5563}}
    @media(max-width:500px){{h1{{font-size:1.7rem}}.book{{flex-direction:column;align-items:flex-start}}.arrow{{display:none}}}}
  </style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div class="tag">Purchase Confirmed</div>
    <h1>Your Toolkit is Ready</h1>
    <p class="sub">The Business Communication Toolkit &mdash; 5 Workbooks + Journal</p>
  </div>
  <div class="books">{books}</div>
  <div class="guarantee">
    <h3>&#127942; 30-Day Money-Back Guarantee</h3>
    <p>If this toolkit does not help you communicate your value more effectively,
    email <a href="mailto:ignis@biztranslation.com">ignis@biztranslation.com</a>
    for a full refund.</p>
  </div>
  <div class="footer"><p>&copy; 2026 Class2Career &nbsp;&middot;&nbsp; By Ignis Spindler, PhD</p></div>
</div>
</body>
</html>"""

_ACCESS_DENIED = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Access Denied | Class2Career</title>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:sans-serif;background:#0A0E1A;color:#FAF7F0;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:2rem;text-align:center}}.wrap{{max-width:440px}}h1{{font-size:1.6rem;margin-bottom:1rem;color:#E8B84B}}p{{color:#9CA3AF;line-height:1.7;margin-bottom:1.25rem}}a{{color:#E8B84B}}</style>
</head><body><div class="wrap"><h1>{title}</h1><p>{msg}</p>
<p>If you believe this is an error, email <a href="mailto:ignis@biztranslation.com">ignis@biztranslation.com</a> with your purchase receipt.</p>
</div></body></html>"""


# ─── Routes ────────────────────────────────────────────────────────────────────
@app.route("/subscribe", methods=["POST"])
def subscribe():
    email = request.form.get("email", "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"error": "Valid email required"}), 400

    cohort = (request.form.get("cohort", "") or
              request.form.get("utm_source", "")).strip()

    is_new = save_lead(
        email,
        cohort=cohort,
        lead_magnet=request.form.get("lead_magnet", ""),
        source_url=request.referrer or "",
        utm_source=request.form.get("utm_source", ""),
        utm_medium=request.form.get("utm_medium", ""),
        utm_campaign=request.form.get("utm_campaign", ""),
    )

    # Generate a per-user download token for the PDF
    dl_token = secrets.token_urlsafe(32)
    c = get_cohort(cohort)
    r_set(f'dl_token:{dl_token}', {'email': email, 'cohort': cohort, 'pdf': c['pdf']}, ex=7776000)  # 90 days

    site_url = os.environ.get('SITE_URL', c['site'])
    download_url = f"{site_url}/download?token={dl_token}&file=lead"

    sent = send_seq_email(email, 1, cohort, download_url=download_url)
    print(f"[Subscribe] {email} cohort={cohort!r} new={is_new} sent={sent}")

    return jsonify({
        "success": True,
        "message": "Check your inbox for the Interview Mastery Guide.",
        "email_sent": sent,
    })


@app.route("/webhook/stripe", methods=["POST"])
def webhook_stripe():
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe_lib.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        abort(400)
    except stripe_lib.error.SignatureVerificationError:
        abort(400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        email = (
            session.get("customer_details", {}).get("email") or
            session.get("customer_email", "")
        )
        cohort = session.get("client_reference_id", "") or ""
        if email:
            token = secrets.token_urlsafe(32)
            save_purchase(email, session["id"], token, cohort=cohort)
            save_lead(email, cohort=cohort, utm_source="stripe_purchase")

            c = get_cohort(cohort)
            site_url = os.environ.get('SITE_URL', c['site'])
            access_url = f"{site_url}/access?token={token}"

            subj, html, txt = email_purchase(c, access_url)
            sent = _send(email, subj, html, txt)
            if sent:
                # Mark all sequence emails as done so no more drip sends go out
                for n in range(1, 7):
                    seq_mark_sent(email, n)
                r_sadd(f'seq:sent:{email}', 'purchased')
            print(f"[Purchase] {email} cohort={cohort!r} sent={sent}")

    return jsonify({"received": True}), 200


@app.route("/cron/send-sequence", methods=["GET", "POST"])
def cron_send_sequence():
    # Verify this is called by Vercel Cron (or manually with secret)
    auth = request.headers.get("Authorization", "")
    if CRON_SECRET and auth != f"Bearer {CRON_SECRET}":
        abort(401)

    now = int(time.time())
    leads = r_smembers('leads:all')
    sent_count = 0
    skip_count = 0
    errors = []

    for email in leads:
        if has_purchased(email):
            skip_count += 1
            continue

        lead_data = r_get(f'lead:{email}')
        cohort = lead_data.get('cohort', '') if lead_data else ''
        subscribed_at = r_get(f'seq:subscribed_at:{email}')
        if not subscribed_at:
            skip_count += 1
            continue

        days_elapsed = (now - int(subscribed_at)) / 86400

        for seq_num in [2, 3, 4, 5, 6]:  # seq 1 is sent on subscribe
            if seq_already_sent(email, seq_num):
                continue
            if days_elapsed >= SEQ_DAYS[seq_num]:
                ok = send_seq_email(email, seq_num, cohort)
                if ok:
                    sent_count += 1
                    print(f"[Cron] Sent seq {seq_num} to {email}")
                else:
                    errors.append(f"{email}:seq{seq_num}")
                break  # only one email per lead per cron run

    return jsonify({
        "sent": sent_count,
        "skipped": skip_count,
        "errors": errors,
        "leads_checked": len(leads),
    })


@app.route("/download", methods=["GET"])
def download():
    token = request.args.get("token", "").strip()
    file_key = request.args.get("file", "").strip()

    if not token:
        abort(400)

    # Lead magnet PDF download
    if file_key == "lead":
        dl_data = r_get(f'dl_token:{token}')
        if not dl_data:
            abort(403)
        pdf_name = dl_data.get('pdf', 'interview-mastery-class2careers.pdf')
        pdf_path = os.path.join(_LEAD_PDF_DIR, pdf_name)
        if not os.path.isfile(pdf_path):
            abort(404)
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=pdf_name,
            mimetype='application/pdf',
        )

    # Workbook HTML download (requires purchase token)
    if file_key in WORKBOOK_FILES:
        token_data = r_get(f'token:{token}')
        if not token_data or not token_data.get('valid'):
            abort(403)
        filename, _ = WORKBOOK_FILES[file_key]
        file_path = os.path.join(_WORKBOOK_DIR, filename)
        if not os.path.isfile(file_path):
            abort(404)
        return send_file(
            file_path,
            mimetype='text/html',
        )

    abort(400)


@app.route("/access", methods=["GET"])
def access():
    token = request.args.get("token", "").strip()
    if not token:
        resp = make_response(
            _ACCESS_DENIED.format(
                title="No Access Token",
                msg="This link is missing an access token. Use the link from your purchase confirmation email."
            ), 403
        )
        resp.headers["Content-Type"] = "text/html"
        return resp

    data = r_get(f"token:{token}")
    if not data or not data.get("valid"):
        resp = make_response(
            _ACCESS_DENIED.format(
                title="Invalid Token",
                msg="This access link is invalid or has expired."
            ), 403
        )
        resp.headers["Content-Type"] = "text/html"
        return resp

    resp = make_response(_access_page_html(token), 200)
    resp.headers["Content-Type"] = "text/html"
    return resp


@app.route("/webhook/stripe/test", methods=["POST"])
def webhook_stripe_test():
    """Dev-only endpoint: simulate a completed Stripe purchase without signature verification."""
    if os.environ.get('FLASK_ENV') != 'development':
        abort(404)
    data = request.get_json(force=True) or {}
    email  = data.get('email', '').strip().lower()
    cohort = data.get('cohort', 'class2careers').strip()
    if not email:
        return jsonify({"error": "email required"}), 400

    token          = secrets.token_urlsafe(32)
    fake_session   = f"cs_test_{secrets.token_hex(8)}"
    save_purchase(email, fake_session, token, cohort=cohort)
    save_lead(email, cohort=cohort, utm_source="stripe_test")

    c          = get_cohort(cohort)
    site_url   = os.environ.get('SITE_URL', c['site'])
    access_url = f"{site_url}/access?token={token}"

    subj, html, txt = email_purchase(c, access_url)
    sent = _send(email, subj, html, txt)
    if sent:
        for n in range(1, 7):
            seq_mark_sent(email, n)
        r_sadd(f'seq:sent:{email}', 'purchased')

    print(f"[TestPurchase] {email} cohort={cohort!r} token={token} sent={sent}")
    return jsonify({
        "success":    True,
        "token":      token,
        "access_url": access_url,
        "email_sent": sent,
    })


@app.route("/stats", methods=["GET"])
def stats():
    cohort_keys   = list(COHORTS.keys())
    leads_total   = r_scard('leads:all')
    purch_total   = r_scard('purchases:all')
    conv          = round(purch_total / leads_total * 100, 1) if leads_total else 0
    by_cohort     = {}
    for k in cohort_keys:
        l = r_scard(f'leads:cohort:{k}')
        p = r_scard(f'purchases:cohort:{k}')
        by_cohort[k] = {
            'leads': l, 'purchases': p,
            'conversion_rate': round(p / l * 100, 1) if l else 0,
        }
    seq_totals = {n: int(_redis('GET', f'seq:total:{n}') or 0) for n in range(1, 7)}

    # Return JSON when called programmatically
    accept = request.headers.get('Accept', '')
    if 'text/html' not in accept:
        return jsonify({
            'leads_total': leads_total, 'purchases_total': purch_total,
            'conversion_rate': conv, 'by_cohort': by_cohort,
            'sequence_sends': seq_totals,
        })

    # ── HTML dashboard ──────────────────────────────────────────────────────────
    cohort_rows = ''.join(
        f'<tr><td>{k}</td><td>{v["leads"]}</td>'
        f'<td>{v["purchases"]}</td><td>{v["conversion_rate"]}%</td></tr>'
        for k, v in by_cohort.items()
    )
    seq_rows = ''.join(
        f'<tr><td>Email {n}</td><td>{SEQ_DAYS[n]}d</td><td>{seq_totals[n]}</td></tr>'
        for n in range(1, 7)
    )
    cron_url = request.host_url.rstrip('/') + '/cron/send-sequence'
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="refresh" content="60">
  <title>Stats Dashboard</title>
  <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;background:#0A0E1A;color:#FAF7F0;padding:2rem 1.5rem}}
    h1{{font-size:1.6rem;color:#E8B84B;margin-bottom:.3rem}}
    .sub{{font-size:.85rem;color:#6B7280;margin-bottom:2rem}}
    .cards{{display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:2rem}}
    .card{{background:#111827;border:1px solid rgba(232,184,75,.15);border-radius:10px;padding:1.25rem 1.75rem;min-width:160px}}
    .card .label{{font-size:.72rem;text-transform:uppercase;letter-spacing:.12em;color:#9CA3AF;margin-bottom:.4rem}}
    .card .value{{font-size:2rem;font-weight:700;color:#E8B84B}}
    .card .sub{{font-size:.8rem;color:#6B7280;margin:0}}
    h2{{font-size:1rem;color:#E8B84B;margin:1.5rem 0 .75rem;text-transform:uppercase;letter-spacing:.08em}}
    table{{width:100%;max-width:680px;border-collapse:collapse;font-size:.9rem;margin-bottom:1.5rem}}
    th{{text-align:left;padding:8px 12px;background:#1F2937;color:#9CA3AF;font-size:.75rem;text-transform:uppercase;letter-spacing:.08em}}
    td{{padding:9px 12px;border-bottom:1px solid rgba(255,255,255,.05);color:#D4CEC3}}
    tr:hover td{{background:rgba(232,184,75,.04)}}
    .btn{{display:inline-block;background:#E8B84B;color:#0A0E1A;padding:10px 20px;font-weight:bold;font-size:.9rem;text-decoration:none;border-radius:7px;border:none;cursor:pointer;margin-top:.5rem}}
    .btn:hover{{background:#d4a83a}}
    .cron-form{{background:#111827;border:1px solid rgba(232,184,75,.12);border-radius:10px;padding:1.25rem 1.5rem;max-width:480px}}
    .cron-form p{{font-size:.85rem;color:#9CA3AF;margin:.5rem 0 1rem}}
    .refresh{{font-size:.75rem;color:#4B5563;margin-top:1.5rem}}
  </style>
</head>
<body>
  <h1>Class2Career Dashboard</h1>
  <p class="sub">Auto-refreshes every 60 seconds &nbsp;&middot;&nbsp; {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}</p>

  <div class="cards">
    <div class="card"><div class="label">Total Leads</div><div class="value">{leads_total}</div></div>
    <div class="card"><div class="label">Purchases</div><div class="value">{purch_total}</div></div>
    <div class="card"><div class="label">Conversion</div><div class="value">{conv}%</div></div>
  </div>

  <h2>By Cohort</h2>
  <table>
    <thead><tr><th>Cohort</th><th>Leads</th><th>Purchases</th><th>Conv %</th></tr></thead>
    <tbody>{cohort_rows}</tbody>
  </table>

  <h2>Sequence Emails Sent</h2>
  <table>
    <thead><tr><th>Email</th><th>Sends After</th><th>Total Sent</th></tr></thead>
    <tbody>{seq_rows}</tbody>
  </table>

  <h2>Cron</h2>
  <div class="cron-form">
    <p>Manually fire the sequence worker to process any overdue emails now.</p>
    <form method="POST" action="{cron_url}">
      <button class="btn" type="submit">Run Sequence Worker Now</button>
    </form>
  </div>

  <p class="refresh">Next auto-refresh in 60 seconds.</p>
</body>
</html>"""
    resp = make_response(html, 200)
    resp.headers['Content-Type'] = 'text/html'
    return resp


# Vercel WSGI entry point
try:
    from vercel.wsgi import Vercel
    app = Vercel(app)
except ImportError:
    pass
