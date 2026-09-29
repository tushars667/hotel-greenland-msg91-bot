# Hotel Green Land — MSG91 webhook bot

This replaces the fragile MSG91 Rule-Based Bot flow with a tiny FastAPI service.

## Desired behavior

- First inbound WhatsApp message can be **anything** → sends Welcome + View Menu.
- Normal free-text after that → **bot stays silent**.
- Tapping menu options → sends the selected photos/rates/location/call/website.
- A human reply from MSG91 Hello → outbound webhook detects it and mutes the bot for 24 hours.
- `menu` or `main menu` → reopens the menu.
- Duplicate MSG91 webhook events are ignored.

## Why two MSG91 webhooks?

MSG91's current Webhook (New) supports both inbound and outbound request events.

Create:

1. **Inbound webhook**
   - Service: WhatsApp
   - Event: `On Inbound Request Received`
   - Method: POST
   - URL: `https://YOUR-RENDER-DOMAIN/webhooks/msg91/inbound`
   - Content-Type: JSON
   - Custom header: `X-Webhook-Secret: <same value as WEBHOOK_SECRET>`

2. **Outbound webhook**
   - Service: WhatsApp
   - Event: `On Outbound Request Received`
   - Method: POST
   - URL: `https://YOUR-RENDER-DOMAIN/webhooks/msg91/outbound`
   - Content-Type: JSON
   - Custom header: `X-Webhook-Secret: <same value as WEBHOOK_SECRET>`

The outbound webhook is what gives us automatic human takeover.

## Important MSG91 / Hello change

Disable the current MSG91 Rule-Based Bot from automatically replying.

Keep:
- WhatsApp number connected to MSG91
- "Allow inbound in Hello" enabled
- Hello inbox for human staff

The FastAPI service becomes the only automated responder.

## Local run

```powershell
cd hotel-greenland-msg91-backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Fill MSG91_AUTHKEY + secrets in .env
uvicorn app.main:app --reload
```

Health:
`http://127.0.0.1:8000/health`

For local webhook testing, expose port 8000 using ngrok or another HTTPS tunnel.

## Render deployment

1. Push this folder to a GitHub repo.
2. Render → New → PostgreSQL.
3. Render → New → Web Service → connect the repo.
4. Runtime: Docker.
5. Add environment variables:
   - `MSG91_AUTHKEY`
   - `MSG91_INTEGRATED_NUMBER=917340316302`
   - `WEBHOOK_SECRET`
   - `ADMIN_SECRET`
   - `DATABASE_URL` = Render PostgreSQL **Internal Database URL**, but change the prefix from `postgres://` or `postgresql://` to `postgresql+psycopg://` if needed.
   - `MENU_RESET_HOURS=24`
   - `HUMAN_TAKEOVER_HOURS=24`
6. Deploy.
7. Open `https://YOUR-SERVICE.onrender.com/health`.
8. Configure the two MSG91 webhooks above.

## Human takeover

When staff replies through MSG91 Hello, the outbound webhook reaches `/webhooks/msg91/outbound`.

If the outbound `requestId` belongs to this bot, it is ignored.

If it does **not** belong to the bot, it is treated as a human-agent reply and that customer is muted from automation for 24 hours.

Manual reset:

```bash
curl -X POST \
  -H "X-Admin-Secret: YOUR_ADMIN_SECRET" \
  https://YOUR-SERVICE.onrender.com/admin/resume/91XXXXXXXXXX
```

## Menu

- Deluxe Room Photos
- Super Deluxe Photos
- Property Location
- Hourly Stays
- Call Representative
- Visit Website

Hourly rates:

**Deluxe**
- 2h ₹600
- 3h ₹700
- 4h ₹800
- 5h ₹900

**Super Deluxe**
- 2h ₹1,000
- 3h ₹1,500
- 4h ₹1,800

## Note about media

The app first tries to send the existing MSG91-hosted images as WhatsApp image messages. If MSG91 rejects the media payload shape for your account/version, it automatically falls back to sending the image URL so testing can continue. Once we capture one successful media API request from your account, we can lock the exact image payload permanently.
