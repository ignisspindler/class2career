# Class2Career Website

## Domains
- **PhD2Pro.com** → phd2pro.html (PhD audience)
- **Transition2Corporate.com** → transition2corporate.html (public sector)
- **Class2Careers.com** → index.html (general audience)

All domains should redirect to the appropriate page with UTM parameters:
```
phd2pro.com → class2careers.com?utm_source=phd2pro
transition2corporate.com → class2careers.com?utm_source=transition2corporate
```

## Setup

### 1. Fix SendGrid API Key
Edit `~/.bashrc`:
```
export SENDGRID_API_KEY='SG.your_key_here'
```
Make sure it's spelled correctly: `SENDGRID` not `SENDGRIP`.

### 2. Install Dependencies
```bash
pip3 install flask sendgrid
```

### 3. Run Server
```bash
source ~/.bashrc
python3 email-server.py
```

### 4. DNS Setup
Point your domain to this server's IP. Configure:
- A record for @ → server IP
- MX records for email → Zoho mail servers

## Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /subscribe` | POST | Capture email, send lead magnet |
| `GET /lead-magnet/<filename>` | GET | Download lead magnet PDF |
| `POST /webhook/stripe` | POST | Handle Stripe purchase webhook |
| `GET /stats` | GET | View subscriber stats |
| `GET /subscribers` | GET | List all subscribers |

## Lead Magnets
Place PDF files in `lead_magnets/` folder:
- `Business Translation Guide.pdf`
- `Value Equation Worksheet.pdf`
- `Corporate Toolkit.pdf`

## Database
SQLite database `subscribers.db` created automatically.

## To-Do
- [ ] Create actual lead magnet PDFs
- [ ] Add Stripe webhook secret verification
- [ ] Add password protection to /stats and /subscribers
- [ ] Set up proper SSL (use Cloudflare or similar)
- [ ] Add domain forwarding in DNS
- [ ] Test email deliverability
