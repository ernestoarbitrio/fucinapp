import base64
import io
import os
from datetime import date, timedelta

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    CondPageBreak,
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from configurazione.models import Configurazione, ConfigurazioneAnnuale


class BorderCanvas(rl_canvas.Canvas):
    def showPage(self):
        B8 = (88 * mm, 55 * mm)
        PAGE = B8
        self.saveState()
        self.setStrokeColor(colors.HexColor("#2c5364"))
        self.setLineWidth(1.5)
        self.rect(2 * mm, 2 * mm, PAGE[0] - 4 * mm, PAGE[1] - 4 * mm)
        self.restoreState()
        super().showPage()

    def save(self):
        super().save()


def genera_pdf_iscrizione(socio, quota):
    config = Configurazione.get()
    config_anno = ConfigurazioneAnnuale.get(quota.anno)
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2.5 * cm,
        leftMargin=2.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2.5 * cm,
    )

    W = A4[0] - 5 * cm  # usable width

    styles = getSampleStyleSheet()

    bold_center = ParagraphStyle(
        "bold_center",
        parent=styles["Normal"],
        fontSize=11,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    normal = ParagraphStyle("normal", parent=styles["Normal"], fontSize=10, leading=16)
    normal_justify = ParagraphStyle(
        "normal_justify",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=15,
        alignment=TA_JUSTIFY,
    )
    small = ParagraphStyle(
        "small", parent=styles["Normal"], fontSize=8.5, leading=13, alignment=TA_JUSTIFY
    )
    right = ParagraphStyle(
        "right", parent=styles["Normal"], fontSize=9.5, leading=14, alignment=TA_RIGHT
    )

    story = []

    # ── HEADER ──────────────────────────────────────────────────────────────
    # logo
    logo_path = None
    if config.logo:
        logo_path = config.logo.path
    else:
        logo_path = os.path.join(
            settings.BASE_DIR, "anagrafica", "static", "anagrafica", "logo-fucina.jpeg"
        )

    # Title centered
    story.append(Paragraph("MODULO DI RICHIESTA TESSERAMENTO", bold_center))
    story.append(Paragraph("ACRAS", bold_center))
    story.append(Spacer(1, 1 * cm))
    address_block = (
        [
            Paragraph("Al Consiglio Direttivo", right),
            Paragraph(f"di {config.nome_associazione}", right),
            Paragraph(f"{config.via}", right),
            Paragraph(f"{config.cap}, {config.comune}", right),
        ],
    )
    # Address + logo on the right
    if os.path.exists(logo_path):
        logo_img = Image(logo_path, width=2.2 * cm, height=2.2 * cm)
        address_data = [["", address_block, logo_img]]
        address_table = Table(address_data, colWidths=[W * 0.55, W * 0.3, W * 0.07])
    else:
        address_data = [["", address_block]]
        address_table = Table(address_data, colWidths=[W * 0.5, W * 0.5])

    address_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(address_table)
    story.append(Spacer(1, 0.5 * cm))
    story.append(
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#aaaaaa"))
    )
    story.append(Spacer(1, 0.6 * cm))

    # ── DATI PERSONALI ───────────────────────────────────────────────────────
    data_nascita = (
        socio.data_nascita.strftime("%d/%m/%Y") if socio.data_nascita else "___________"
    )
    luogo_nascita = socio.luogo_nascita or "___________"
    indirizzo = f"{socio.via}, {socio.cap} {socio.comune} - {socio.provincia}"
    cf = socio.codice_fiscale or "___________"
    email = socio.email or "___________"
    delta = config_anno.delta_giorni_iscrizione
    data_doc = (
        quota.data_pagamento - timedelta(days=delta)
        if quota.data_pagamento
        else quota.data_inizio - timedelta(days=delta)
        if quota.data_inizio
        else socio.created_at
    )
    if data_doc.year != quota.anno and quota.data_inizio:
        data_doc = quota.data_inizio
    data_doc = data_doc.strftime("%d/%m/%Y")

    story.append(
        Paragraph(
            f"Io sottoscritto <b>{socio.nome} {socio.cognome}</b>, nato a "
            f"{luogo_nascita} il {data_nascita} e residente in {indirizzo}. "
            f"Codice Fiscale: {cf}, email: {email}, telefono: {socio.telefono or '-'}",
            normal_justify,
        )
    )

    story.append(Spacer(1, 0.5 * cm))

    # ── DICHIARAZIONE ────────────────────────────────────────────────────────
    story.append(
        Paragraph(
            "Avendo preso visione dello statuto, chiedo di poter aderire all'associazione in qualità di socio ordinario. "
            "A tale scopo, dichiaro di condividere gli obiettivi espressi nello statuto e di voler contribuire alla loro "
            "realizzazione. Inoltre:",
            normal_justify,
        )
    )
    story.append(Spacer(1, 0.3 * cm))
    story.append(
        Paragraph(
            "a) mi impegno nell'osservanza delle norme statutarie e delle disposizioni del consiglio direttivo;",
            normal_justify,
        )
    )
    story.append(
        Paragraph(
            "b) dichiaro che in caso di accettazione quale socio-ordinario verserà la quota associativa annuale secondo le modalità stabilite dal consiglio direttivo.",
            normal_justify,
        )
    )
    story.append(Spacer(1, 0.7 * cm))

    # ── DATA E FIRMA ─────────────────────────────────────────────────────────
    firma_row_data = [
        [
            Paragraph(f"Data &nbsp;&nbsp; <b>{data_doc}</b>", normal),
            Paragraph("Firma", normal),
        ]
    ]
    if socio.firma:
        try:
            firma_data = socio.firma
            if "," in firma_data:
                firma_data = firma_data.split(",")[1]
            firma_bytes = base64.b64decode(firma_data)
            firma_buffer = io.BytesIO(firma_bytes)
            firma_img = Image(firma_buffer, width=6 * cm, height=2 * cm)
            firma_row_data = [
                [
                    Paragraph(f"Data &nbsp;&nbsp; <b>{data_doc}</b>", normal),
                    firma_img,
                ]
            ]
        except Exception:
            pass

    firma_table = Table(firma_row_data, colWidths=[W * 0.4, W * 0.6])
    firma_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("LINEBELOW", (1, 0), (1, 0), 0.5, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(firma_table)
    story.append(Spacer(1, 0.8 * cm))
    story.append(
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#ffffff"))
    )
    story.append(Spacer(1, 0.5 * cm))

    # ── PRIVACY ──────────────────────────────────────────────────────────────
    story.append(
        Paragraph(
            f"Il sottoscritto, ai sensi dell'art. 13 del Regolamento Europeo 2016/679, dichiara di aver preso visione "
            f"dell'informativa sul trattamento dei dati personali e autorizza il circolo alla raccolta e al trattamento dei "
            f"dati forniti per l'invio tramite e-mail, sms o telefono, eventualmente conferiti, di comunicazioni inerenti "
            f"l'attività statutaria e regolamentare da parte dell'Associazione di Promozione Sociale {config.nome_associazione}.",
            small,
        )
    )
    story.append(Spacer(1, 0.3 * cm))

    consensi_text = []
    consensi_text.append(
        Paragraph(
            f"Consenso newsletter e comunicazioni promozionali: <b>{'SI' if socio.consenso_marketing else 'NO'}</b>",
            small,
        )
    )
    consensi_text.append(
        Paragraph(
            f"Consenso uso immagini fotografiche e video: <b>{'SI' if socio.consenso_immagini else 'NO'}</b>",
            small,
        )
    )
    story.extend(consensi_text)
    story.append(Spacer(1, 0.6 * cm))

    # Privacy firma
    privacy_firma_data = [
        [
            Paragraph("", normal),
            Paragraph("Firma", normal),
        ]
    ]
    if socio.firma:
        try:
            firma_data = socio.firma
            if "," in firma_data:
                firma_data = firma_data.split(",")[1]
            firma_bytes = base64.b64decode(firma_data)
            firma_buffer = io.BytesIO(firma_bytes)
            firma_img2 = Image(firma_buffer, width=6 * cm, height=2 * cm)
            privacy_firma_data = [[Paragraph("", normal), firma_img2]]
        except Exception:
            pass

    privacy_firma_table = Table(privacy_firma_data, colWidths=[W * 0.4, W * 0.6])
    privacy_firma_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("LINEBELOW", (1, 0), (1, 0), 0.5, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(privacy_firma_table)

    # ── FOOTER ───────────────────────────────────────────────────────────────
    def add_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#444444"))
        canvas.line(2.5 * cm, 1.7 * cm, A4[0] - 2.5 * cm, 1.7 * cm)
        canvas.drawCentredString(
            A4[0] / 2,
            1.4 * cm,
            f"{config.nome_associazione}, {config.via},{config.cap} {config.comune} | C.F. {config.cf}",
        )
        canvas.drawCentredString(
            A4[0] / 2,
            0.9 * cm,
            f"mail: {config.email} | pec: {config.pec}",
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    buffer.seek(0)
    return buffer


def genera_pdf_elenco_soci(soci_queryset, anno):
    from django.utils import timezone
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import LongTable

    if anno is None:
        anno = timezone.now().year
    config = Configurazione.get()
    config_anno = ConfigurazioneAnnuale.get(anno)

    buffer = io.BytesIO()
    today = date.today()

    PAGE = landscape(A4)

    class NumberedCanvas(rl_canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total_pages = len(self._saved_page_states)
            for i, state in enumerate(self._saved_page_states):
                self.__dict__.update(state)
                self.draw_footer(i + 1, total_pages)
                super().showPage()
            super().save()

        def draw_footer(self, page_num, total):
            self.saveState()
            self.setFont("Helvetica", 7)
            self.setFillColor(colors.HexColor("#666666"))
            self.line(2 * cm, 1.2 * cm, PAGE[0] - 2 * cm, 1.2 * cm)
            self.drawCentredString(
                PAGE[0] / 2,
                0.8 * cm,
                f"{config.nome_associazione} · {config.via}, {config.cap} {config.comune} · C.F. {config.cf} · "
                f"Generato il {today.strftime('%d/%m/%Y')} · Pagina {page_num} di {total}",
            )
            self.restoreState()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=PAGE,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=1.5 * cm,
        bottomMargin=2 * cm,
    )
    W = PAGE[0] - 3 * cm
    styles = getSampleStyleSheet()

    tiny = ParagraphStyle("tiny", parent=styles["Normal"], fontSize=6.5, leading=8)
    tiny_bold = ParagraphStyle(
        "tiny_bold",
        parent=styles["Normal"],
        fontSize=6.5,
        leading=8,
        fontName="Helvetica-Bold",
    )
    header_style = ParagraphStyle(
        "header_style",
        parent=styles["Normal"],
        fontSize=7,
        leading=9,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )
    title_style = ParagraphStyle(
        "title_style",
        parent=styles["Normal"],
        fontSize=11,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        "sub_style",
        parent=styles["Normal"],
        fontSize=9,
        alignment=TA_CENTER,
        spaceAfter=2,
    )

    story = []

    # Header
    logo_path = None
    if config.logo:
        logo_path = config.logo.path
    else:
        logo_path = os.path.join(
            settings.BASE_DIR, "anagrafica", "static", "anagrafica", "logo-fucina.jpeg"
        )
    if os.path.exists(logo_path):
        logo_img = Image(logo_path, width=1.8 * cm, height=1.8 * cm)
        logo_img.hAlign = "CENTER"

    header_data = [
        [
            logo_img if os.path.exists(logo_path) else Paragraph("", tiny),
            [
                Paragraph(
                    f"ASSOCIAZIONE: {config.nome_associazione.upper()}", title_style
                ),
                Paragraph(f"TESSERAMENTO {anno}/{str(anno + 1)[-2:]}", sub_style),
                Paragraph(f"LOCALITA': {config.comune.upper()}", sub_style),
            ],
            Paragraph("", tiny),
        ]
    ]
    header_table = Table(header_data, colWidths=[2 * cm, W - 4 * cm, 2 * cm])
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(header_table)
    story.append(Spacer(1, 0.3 * cm))

    # Table header
    col_headers = [
        Paragraph("N.\nTess.", header_style),
        Paragraph("Data\nTess.", header_style),
        Paragraph("Cognome e Nome", header_style),
        Paragraph("Luogo e data\ndi nascita", header_style),
        Paragraph("Codice Fiscale", header_style),
        Paragraph("Qual.", header_style),
        Paragraph("Residenza", header_style),
        Paragraph("Prov.", header_style),
        Paragraph("Comune", header_style),
    ]

    col_widths = [
        1.2 * cm,
        1.9 * cm,
        5 * cm,
        3.5 * cm,
        3.2 * cm,
        1 * cm,
        6.5 * cm,
        1 * cm,
        3.2 * cm,
    ]

    rows = [col_headers]

    for socio in soci_queryset:
        quota_corrente = socio.quote.filter(stato="pagata", anno=anno).first()
        numero_tessera = str(quota_corrente.pk)
        data_tess = (
            quota_corrente.data_pagamento.strftime("%d/%m/%y")
            if quota_corrente and quota_corrente.data_pagamento
            else (socio.created_at.strftime("%d/%m/%y") if socio.created_at else "")
        )
        luogo_nascita = f"{socio.luogo_nascita}\n{socio.data_nascita.strftime('%d/%m/%y') if socio.data_nascita else ''}"
        residenza = f"{socio.via or ''}"
        comune = f"{socio.comune or ''}"
        prov = f"{socio.provincia or ''}"

        row = [
            Paragraph(numero_tessera, tiny),
            Paragraph(data_tess, tiny),
            Paragraph(f"{socio.cognome} {socio.nome}", tiny_bold),
            Paragraph(luogo_nascita, tiny),
            Paragraph(socio.codice_fiscale or "", tiny),
            Paragraph(socio.tipo or "SO", tiny),
            Paragraph(residenza, tiny),
            Paragraph(prov, tiny),
            Paragraph(comune, tiny),
        ]
        rows.append(row)

    table = LongTable(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#778899")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#aaaaaa")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f5f8fa")],
                ),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (1, -1), "CENTER"),
                ("ALIGN", (5, 0), (5, -1), "CENTER"),
                ("ALIGN", (7, 0), (7, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )

    story.append(table)
    story.append(Spacer(1, 0.5 * cm))

    story.append(
        Paragraph(
            "Qual.: VP Vice Presidente · CO Consigliere · SG Segretario · DS Direttore Sportivo · "
            "GA Giudice Arbitro · MS Medico Sportivo · SO Socio Ordinario · SJ Socio Junior · AT Atleta",
            ParagraphStyle(
                "legend",
                parent=styles["Normal"],
                fontSize=6.5,
                textColor=colors.HexColor("#666666"),
            ),
        )
    )
    # Add page break only if not enough space for the boxes
    story.append(CondPageBreak(5 * cm))
    story.append(Spacer(1, 0.5 * cm))

    # Timbro and Firma boxes as a table
    box_style = ParagraphStyle(
        "box_title",
        parent=styles["Normal"],
        fontSize=8,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )
    # Build firma cell content
    firma_cell_content = [Paragraph("FIRMA", box_style)]
    if config_anno.firma_presidente and config_anno.firma_presidente.name:
        try:
            firma_img = Image(
                config_anno.firma_presidente.path,
                width=5 * cm,
                height=1.2 * cm,
            )
            firma_img.hAlign = "CENTER"
            firma_cell_content.append(Spacer(1, 0.1 * cm))
            firma_cell_content.append(firma_img)
        except Exception:
            firma_cell_content.append(Spacer(1, 1.5 * cm))
    else:
        firma_cell_content.append(Spacer(1, 1.5 * cm))

    boxes_data = [
        [
            [Paragraph("TIMBRO", box_style), Spacer(1, 1.5 * cm)],
            Paragraph("", tiny),
            firma_cell_content,
        ]
    ]
    boxes_table = Table(boxes_data, colWidths=[6 * cm, 2 * cm, 6 * cm])
    boxes_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (0, 0), 0.8, colors.black),
                ("BOX", (2, 0), (2, 0), 0.8, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    story.append(boxes_table)

    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer


def genera_pdf_tessera(socio, quota):
    config = Configurazione.get()
    buffer = io.BytesIO()

    # B8 size: 88mm x 62mm (landscape)
    B8 = (88 * mm, 55 * mm)
    PAGE = B8

    doc = SimpleDocTemplate(
        buffer,
        pagesize=PAGE,
        rightMargin=4 * mm,
        leftMargin=4 * mm,
        topMargin=1 * mm,
        bottomMargin=1 * mm,
    )

    W = PAGE[0] - 8 * mm

    styles = getSampleStyleSheet()

    center_title = ParagraphStyle(
        "center_title",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=8,
        leading=10,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#2c5364"),
    )
    small = ParagraphStyle(
        "small",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=5.5,
        leading=7,
        textColor=colors.HexColor("#666666"),
    )
    label_style = ParagraphStyle(
        "label",
        parent=styles["Normal"],
        fontSize=5,
        leading=6,
        textColor=colors.HexColor("#888888"),
    )
    value_style = ParagraphStyle(
        "value",
        parent=styles["Normal"],
        fontSize=6.5,
        leading=8,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#222222"),
    )

    story = []

    # ── PAGE 1: Front — Logos ─────────────────────────────────────────────────
    # Logo principale
    logo_path = None
    if config.logo:
        logo_path = config.logo.path
    else:
        logo_path = os.path.join(
            settings.BASE_DIR, "anagrafica", "static", "anagrafica", "logo-fucina.jpeg"
        )

    if os.path.exists(logo_path):
        logo_left = Image(logo_path, width=18 * mm, height=18 * mm)
    # Logo secondario
    if config.logo_secondario:
        try:
            logo_right = Image(
                config.logo_secondario.path, width=20 * mm, height=14 * mm
            )
        except Exception:
            pass
    logos_data = [[logo_left, Paragraph("", small), logo_right]]
    logos_table = Table(logos_data, colWidths=[14 * mm, W - 30 * mm, 20 * mm])
    logos_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(logos_table)
    story.append(Spacer(1, 2 * mm))

    story.append(
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#2c5364"))
    )
    story.append(Spacer(1, 2 * mm))

    story.append(Paragraph("TESSERA ASSOCIATIVA", center_title))
    story.append(Spacer(1, 2 * mm))

    story.append(
        HRFlowable(
            width="100%",
            thickness=0.5,
            color=colors.HexColor("#2c5364"),
        )
    )
    story.append(Spacer(1, 2 * mm))
    # QR code + numero tessera on the same row
    qr_cell = Paragraph("", small)
    if socio.qr_code and os.path.exists(socio.qr_code.path):
        try:
            qr_cell = Image(socio.qr_code.path, width=17 * mm, height=17 * mm)
        except Exception:
            pass

    numero_style = ParagraphStyle(
        "numero",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=14,
        leading=16,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#2c5364"),
    )
    numero_label = ParagraphStyle(
        "numero_label",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=6,
        leading=7,
        textColor=colors.HexColor("#888888"),
    )

    qr_row = [
        [
            qr_cell,
            Paragraph("", small),
            [
                Paragraph("N° TESSERA", numero_label),
                Paragraph(str(quota.pk), numero_style),
            ],
        ]
    ]
    qr_table = Table(qr_row, colWidths=[17 * mm, W - 37 * mm, 20 * mm])
    qr_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (2, 0), (2, 0), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(qr_table)

    # ── PAGE 2: Back — Info ───────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Spacer(1, 2 * mm))

    anno = f"{quota.anno}/{quota.anno + 1}"
    inizio = quota.data_inizio.strftime("%d/%m/%Y") if quota.data_inizio else "-"
    indirizzo = f"{socio.via or ''}, {socio.comune or ''} ({socio.provincia or ''})"

    rows = [
        [
            Paragraph("SOCIO", label_style),
            Paragraph(f"{socio.cognome} {socio.nome}", value_style),
        ],
        [Paragraph("INDIRIZZO", label_style), Paragraph(indirizzo, value_style)],
        [
            Paragraph("CATEGORIA", label_style),
            Paragraph(
                socio.get_tipo_display() if socio.tipo else "Socio Ordinario",
                value_style,
            ),
        ],
        [Paragraph("N° TESSERA", label_style), Paragraph(str(quota.pk), value_style)],
        [Paragraph("ANNO", label_style), Paragraph(str(anno), value_style)],
        [Paragraph("DATA DI ADESIONE", label_style), Paragraph(inizio, value_style)],
    ]

    t = Table(rows, colWidths=[20 * mm, W - 20 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f5f5f5")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#eeeeee")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 3 * mm))

    doc.build(story, canvasmaker=BorderCanvas)
    buffer.seek(0)
    return buffer
