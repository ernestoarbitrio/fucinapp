import base64

import resend
from django.conf import settings

from anagrafica.pdf_utils import genera_pdf_tessera
from configurazione.models import Configurazione


def invia_email_iscrizione(socio, quota):
    try:
        config = Configurazione.get()

        subject = f"Conferma iscrizione — {config.nome_associazione}"

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:#f5f5f5; padding:20px; }}
        .card {{ background:white; border-radius:12px; padding:32px; max-width:520px; margin:0 auto; box-shadow:0 2px 12px rgba(0,0,0,0.08); }}
        h1 {{ color:#2c5364; font-size:1.4rem; margin-bottom:4px; }}
        p {{ color:#555; font-size:0.95rem; line-height:1.6; }}
        .badge {{ display:inline-block; background:#e6f4ea; color:#2e7d32; border-radius:20px; padding:4px 14px; font-size:0.85rem; font-weight:600; margin:12px 0; }}
        table {{ width:100%; border-collapse:collapse; margin:16px 0; }}
        td {{ padding:8px 12px; border-bottom:1px solid #eee; font-size:0.9rem; }}
        td:first-child {{ color:#888; font-weight:500; width:40%; }}
        td:last-child {{ color:#222; font-weight:600; }}
        .footer {{ text-align:center; font-size:0.78rem; color:#aaa; margin-top:24px; }}
    </style>
</head>
<body>
<div class="card">
    <h1>Benvenuto/a, {socio.nome}! 🎉</h1>
    <p>La tua iscrizione a <strong>{config.nome_associazione}</strong> è stata completata con successo.</p>
    <div class="badge">✅ Iscrizione confermata</div>

    <table>
        <tr><td>Nome e Cognome</td><td>{socio.nome_completo}</td></tr>
        <tr><td>Codice Fiscale</td><td>{socio.codice_fiscale}</td></tr>
        <tr><td>Email</td><td>{socio.email}</td></tr>
        <tr><td>N° Tessera</td><td>{quota.pk}</td></tr>
        <tr><td>Anno</td><td>{quota.anno}</td></tr>
    </table>

    <p>In allegato trovi la tua tessera associativa.</p>

    <div class="footer">
        {config.nome_associazione} · {config.via}, {config.cap} {config.comune}<br>
        {config.email}
    </div>
</div>
</body>
</html>
        """
        resend.api_key = settings.RESEND_API_KEY
        pdf_tessera = genera_pdf_tessera(socio, quota)
        resend.Emails.send(
            {
                "from": settings.DEFAULT_FROM_EMAIL,
                "to": [socio.email],
                "subject": subject,
                "html": html_body,
                "attachments": [
                    {
                        "filename": f"tessera_{socio.cognome}_{socio.nome}.pdf",
                        "content": base64.b64encode(pdf_tessera.getvalue()).decode(
                            "utf-8"
                        ),
                    }
                ],
            }
        )

    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Errore invio email iscrizione: {e}")
