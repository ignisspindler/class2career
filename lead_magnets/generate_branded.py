#!/usr/bin/env python3
"""
Generate 4 branded Interview Mastery Guide HTML files.
Run from: biztranslation/website/lead_magnets/
"""
import re, os

BASE = os.path.join(os.path.dirname(__file__), 'interview-mastery-guide.html')
with open(BASE, 'r') as f:
    template = f.read()

brands = [
    {
        'slug':       'biztranslation',
        'title':      'Interview Mastery Guide | BizTranslation',
        'cover_img':  '../assets/covers/cover-img-biztranslation.png',
        'cover_alt':  'Interview Mastery Guide — BizTranslation',
        'intro_p1':   'This guide distills the core interview frameworks from the BizTranslation workbook series into one actionable reference. Print it, mark it up, and work through each section before your next interview.',
        'intro_p2':   'The goal is not to answer questions well. The goal is to walk into the room already thinking like someone who belongs there.',
        'cta_h2':     'Ready to Go Deeper?',
        'cta_p':      'The full BizTranslation workbook series covers every dimension of this transition: business fundamentals, sales strategy, value communication, product thinking, and personal growth.',
        'cta_url':    'https://biztranslation.com',
        'cta_label':  'biztranslation.com',
    },
    {
        'slug':       'class2careers',
        'title':      'Interview Mastery Guide | Class2Careers',
        'cover_img':  '../assets/covers/cover-img-class2careers.png',
        'cover_alt':  'Interview Mastery Guide — Class2Careers',
        'intro_p1':   'Built for graduates entering the workforce. You have the skills. This guide teaches you how to present them in a way that gets you hired and gets you paid.',
        'intro_p2':   'Your GPA will not close a job offer. The way you frame your experience will. Work through each phase before your next interview.',
        'cta_h2':     'Ready to Turn Your Degree Into an Offer?',
        'cta_p':      'The full Class2Careers toolkit covers every step: understanding how businesses work, communicating your value, and negotiating the salary you deserve.',
        'cta_url':    'https://class2careers.com',
        'cta_label':  'class2careers.com',
    },
    {
        'slug':       'phd2pro',
        'title':      'Interview Mastery Guide | PhD2Pro',
        'cover_img':  '../assets/covers/cover-img-phd2pro.png',
        'cover_alt':  'Interview Mastery Guide — PhD2Pro',
        'intro_p1':   'Built for researchers and academics making the move to industry. Your expertise is real. The problem is that interviewers cannot see it until you translate it.',
        'intro_p2':   'This guide gives you the frameworks to do that translation — so you walk into every interview thinking like someone who already belongs in the room.',
        'cta_h2':     'Ready to Make the Full Transition?',
        'cta_p':      'The full PhD2Pro workbook series gives you the complete system: business fundamentals, value communication, the sales mindset, and the personal growth frameworks that separate PhDs who thrive in industry from those who stay stuck.',
        'cta_url':    'https://phd2pro.com',
        'cta_label':  'phd2pro.com',
    },
    {
        'slug':       'transition2corporate',
        'title':      'Interview Mastery Guide | Transition2Corporate',
        'cover_img':  '../assets/covers/cover-img-transition2corporate.png',
        'cover_alt':  'Interview Mastery Guide — Transition2Corporate',
        'intro_p1':   'Built for public sector professionals moving into the private sector. You have managed real programs, real budgets, and real stakeholders. Private-sector interviewers cannot see that until you speak their language.',
        'intro_p2':   'This guide gives you the translation layer — so every government or nonprofit experience lands as a business asset.',
        'cta_h2':     'Ready to Make the Full Move?',
        'cta_p':      'The Transition2Corporate workbook series covers the complete playbook: business fundamentals, value communication, sales thinking, and the political fluency that makes career changers thrive.',
        'cta_url':    'https://transition2corporate.com',
        'cta_label':  'transition2corporate.com',
    },
]

COVER_BLOCK = '''<!-- ── COVER ─────────────────────────────────────────────────────────── -->
<div class="cover">
  <img src="{cover_img}" alt="{cover_alt}">
</div>

<!-- ── INTRODUCTION ──────────────────────────────────────────────────── -->
<h1>How to Use This Guide</h1>

<div class="intro-box">
  <p>{intro_p1}</p>
  <p>{intro_p2}</p>
</div>'''

CTA_BLOCK = '''<!-- ── FINAL CTA ───────────────────────────────────────────────────────── -->
<div class="cta-box">
  <h2>{cta_h2}</h2>
  <p>{cta_p}</p>
  <a class="cta-url" href="{cta_url}">{cta_label}</a>
</div>'''

# Regex patterns to replace the variable sections
COVER_PAT = re.compile(
    r'<!-- ── COVER ─+.*?<!-- ── INTRODUCTION ─+.*?</div>\n</div>\n',
    re.DOTALL
)
CTA_PAT = re.compile(
    r'<!-- ── FINAL CTA ─+.*?</div>\n\n</body>',
    re.DOTALL
)
TITLE_PAT = re.compile(r'<title>.*?</title>')

for b in brands:
    html = template

    # Replace title
    html = TITLE_PAT.sub(f'<title>{b["title"]}</title>', html)

    # Replace cover + intro block
    new_cover = COVER_BLOCK.format(**b) + '\n'
    html = COVER_PAT.sub(new_cover, html)

    # Replace CTA block
    new_cta = CTA_BLOCK.format(**b) + '\n\n</body>'
    html = CTA_PAT.sub(new_cta, html)

    out = os.path.join(os.path.dirname(__file__), f'interview-mastery-{b["slug"]}.html')
    with open(out, 'w') as f:
        f.write(html)
    print(f'Wrote {out}')

print('Done.')
