# N8N Content Approval Pipeline

## Overview

This workflow manages content creation → review → scheduling → tracking for Class2Career social media.

---

## Workflow 1: Content Generation & Review Queue

### Trigger
- **Manual trigger** (button in n8n dashboard) OR
- **Scheduled** (every Monday, generate week's content)

### Steps

```
1. [Manual Trigger / Schedule]
        ↓
2. [HTTP Request → Claude API]
    Generate 7 social posts (2 for X, 2 for LinkedIn, 2 for TikTok, 1 for Instagram)
    Include: post text, hashtags, recommended posting time, image suggestions
    
        ↓
3. [Google Sheets → Append Row]
    Add generated posts to "Content Queue" sheet
    Columns: Post ID, Platform, Content, Image URL, Hashtags, Status, Created, Scheduled
    
        ↓
4. [Email → Send to Reviewer]
    Subject: "Content Ready for Review"
    Body: Link to Google Sheet with pending posts
    + Summary of what was generated
    
        ↓
5. [Wait for Approval]
    → Webhook listener for approval callback
```

### Google Sheet Structure

| Post ID | Platform | Content | Image URL | Hashtags | Status | Created | Scheduled |
|---------|----------|---------|----------|----------|--------|---------|-----------|
| 001 | X | "..." | "url" | "#..." | pending | date | |
| 002 | LinkedIn | "..." | "url" | "#..." | approved | date | |

**Status options:** pending | approved | rejected | scheduled

---

## Workflow 2: Approval Handler

### Trigger
- **Webhook** receives approval signal
- OR manual button in Google Sheet

### Steps

```
1. [Webhook / Manual Trigger]
        ↓
2. [Google Sheets → Read Row]
    Get post details by Post ID
    
        ↓
3. [Switch Node: Status]
    ├── "approved" → Workflow 3 (Schedule)
    ├── "rejected" → Workflow 4 (Archive)
    └── "needs_revision" → Workflow 5 (Revise)
```

---

## Workflow 3: Schedule to Later.com

### Trigger
- Receives approved post from Workflow 2

### Steps

```
1. [Receive data from Workflow 2]
        ↓
2. [Later.com API → Create Post]
    POST /v1/media
    Body: {
        "calendar_id": "xxx",
        "media_url": "image_url",
        "post_details": {
            "text": "content",
            "hashtags": ["tag1", "tag2"]
        },
        "profile_ids": ["profile_id"],
        "publish_at": "ISO_timestamp"
    }
    
        ↓
3. [Google Sheets → Update Row]
    Status: "scheduled"
    Scheduled: timestamp
    
        ↓
4. [Notification → Email/Slack]
    "Post scheduled for [date]"
```

### Later.com Setup Notes

- Get API key from Later.com → Settings → API
- Profile IDs for each social account
- Calendar ID for each platform's calendar

---

## Workflow 4: Rejection Handler

### Steps

```
1. [Receive rejected post]
        ↓
2. [Google Sheets → Update Row]
    Status: "rejected"
    
        ↓
3. [Notification → Email]
    "Post rejected. Logged for review."
```

---

## Workflow 5: Revision Request

### Steps

```
1. [Receive revision request]
        ↓
2. [HTTP Request → Claude API]
    "Revise this post based on feedback: [feedback_text]"
    
        ↓
3. [Google Sheets → Update Row]
    Content: revised content
    Status: "pending_revision"
    
        ↓
4. [Email → Notify]
    "Post revised. Please review again."
```

---

## Workflow 6: Content Discovery Trigger (Optional)

### For monitoring hashtags/keywords

### Steps

```
1. [X API → Search Recent]
    Query: "#CareerTransition OR #PhDLife OR #AcademicToIndustry"
    
        ↓
2. [Filter]
    Only new tweets (since last run)
    
        ↓
3. [Google Sheets → Log Tweet]
    Columns: Tweet ID, Author, Content, Link, Logged At
    
        ↓
4. [Notification → Email/Slack]
    "X mentions found: [count]"
    Body: List of tweets to review
```

---

## Google Sheets Setup

### Sheet 1: Content Queue
Columns: Post ID, Platform, Content, Image URL, Hashtags, Status, Created, Scheduled, Notes

### Sheet 2: Tweet Discovery Log
Columns: Tweet ID, Author, Content, Link, Logged At, Engaged (Y/N)

### Sheet 3: Publishing Calendar
Columns: Date, Platform, Post ID, Content, Status, Published At, Performance

---

## N8N Setup Checklist

### Credentials Needed
- [ ] Google Sheets API (Service Account)
- [ ] Later.com API Key
- [ ] Email (Gmail SMTP or SendGrid)
- [ ] Claude API Key (for content generation)

### Webhooks
- [ ] Approval webhook URL (paste into Google Sheets button/script)
- [ ] Manual trigger URL (for n8n dashboard)

### Variables to Configure
- [ ] Later.com calendar_id
- [ ] Later.com profile_ids (X, LinkedIn, Instagram, TikTok)
- [ ] Google Sheet IDs
- [ ] Reviewer email address
- [ ] Posting schedule (times for each platform)

---

## Posting Schedule Template

| Day | X | LinkedIn | TikTok | Instagram |
|-----|---|----------|--------|----------|
| Monday | 9am, 5pm | 10am | 6pm | - |
| Tuesday | 9am, 5pm | 10am | - | 7pm |
| Wednesday | 9am, 5pm | 10am | 6pm | - |
| Thursday | 9am, 5pm | 10am | - | 7pm |
| Friday | 9am, 3pm | - | 6pm | - |

---

## Environment Variables

```bash
# Google Sheets
GOOGLE_SERVICE_ACCOUNT_KEY=...
GOOGLE_SHEET_ID_CONTENT=...
GOOGLE_SHEET_ID_DISCOVERY=...

# Later.com
LATER_API_KEY=...
LATER_PROFILE_ID_X=...
LATER_PROFILE_ID_LINKEDIN=...
LATER_PROFILE_ID_INSTAGRAM=...
LATER_PROFILE_ID_TIKTOK=...

# Notifications
SMTP_HOST=...
SMTP_USER=...
SMTP_PASS=...
REVIEWER_EMAIL=...

# Claude
CLAUDE_API_KEY=...
```

---

## Troubleshooting

### Later.com API Errors
- Check API key is valid
- Verify profile_id matches the correct social account
- Calendar must be shared with the API user

### Google Sheets Not Updating
- Verify service account has editor access to sheet
- Check sheet ID is correct

### Content Not Generating
- Verify Claude API key
- Check rate limits
- Review prompt in HTTP node

---

## n8n Version Notes

Tested with n8n v1.x. Workflow structure uses core nodes that are stable:
- HTTP Request
- Google Sheets
- Email
- Webhook
- Switch
- Function/Code

Avoid relying on beta nodes or community nodes for critical paths.
