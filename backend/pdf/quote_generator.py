"""Génération devis White Label PDF (ReportLab)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from services.data_loader import _parse_price, data_loader

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output" / "quotes"

BRAND_PRIMARY = colors.HexColor("#0c4a6e")
BRAND_ACCENT = colors.HexColor("#0284c7")
BRAND_MUTED = colors.HexColor("#64748b")


@dataclass
class QuoteLine:
    activity_id: str
    titre: str
    duree: str
    prix_net: float | None
    prix_public: float | None
    langues: str
    zone: str
    conditions_annulation: str = ""


@dataclass
class QuoteDocument:
    devis_ref: str
    date_emission: date
    validite_jours: int
    destination: str
    partner_name: str
    partner_contact: str = ""
    profil_voyageur: str = ""
    duree: str = ""
    taille_groupe: str = ""
    envies: str = ""
    lines: list[QuoteLine] = field(default_factory=list)

    @property
    def valid_until(self) -> date:
        return self.date_emission + timedelta(days=self.validite_jours)

    @property
    def total_net(self) -> float:
        return sum(line.prix_net or 0.0 for line in self.lines)

    @property
    def total_public(self) -> float:
        return sum(line.prix_public or 0.0 for line in self.lines)


def _safe_filename(devis_ref: str) -> str:
    cleaned = re.sub(r"[^\w\-]", "_", devis_ref.strip())
    return f"{cleaned}.pdf"


def _format_eur(amount: float | None) -> str:
    if amount is None or amount <= 0:
        return "Sur demande"
    return f"{amount:,.2f} €".replace(",", " ").replace(".", ",")


def _profil_label(profil: str) -> str:
    labels = {
        "couple": "Couple",
        "famille": "Famille",
        "solo": "Solo",
        "groupe": "Groupe",
        "groupe_amis": "Groupe d'amis",
        "seminaire": "Séminaire / incentive",
    }
    return labels.get(profil, profil.replace("_", " ").title() if profil else "—")


def build_quote_document(
    *,
    devis_ref: str,
    destination: str,
    activity_ids: list[str],
    partner_id: str | None = None,
    nom_agence: str | None = None,
    profil_voyageur: str = "",
    duree: str = "",
    taille_groupe: str = "",
    envies: str = "",
    validite_jours: int = 7,
    emission_date: date | None = None,
) -> QuoteDocument:
    partner_name = (nom_agence or "").strip() or "Votre agence"
    partner_contact = ""
    if partner_id:
        partner = data_loader.get_partner_by_id(partner_id)
        if partner:
            partner_name = partner.get("nom_agence") or partner.get("nom_complet") or partner_name
            partner_contact = partner.get("contact", "") or ""

    lines: list[QuoteLine] = []
    for aid in activity_ids:
        row = data_loader.get_activity_by_id(aid)
        if not row:
            continue
        dest = data_loader.get_destination_by_id(row.get("destination_id", ""))
        zone = (dest or {}).get("nom", "") or destination
        policy = data_loader.get_policy_by_activity_id(aid)
        conditions = ""
        if policy:
            conditions = policy.get("conditions_annulation", "") or ""
        elif row.get("conditions_annulation"):
            conditions = row["conditions_annulation"]

        lines.append(
            QuoteLine(
                activity_id=aid,
                titre=row.get("titre", ""),
                duree=row.get("duree", "") or "—",
                prix_net=_parse_price(row.get("prix")),
                prix_public=_parse_price(row.get("prix_public")),
                langues=row.get("langues", "") or "—",
                zone=zone,
                conditions_annulation=conditions,
            )
        )

    if not lines:
        raise ValueError("Aucune activité valide pour ce devis.")

    return QuoteDocument(
        devis_ref=devis_ref,
        date_emission=emission_date or date.today(),
        validite_jours=validite_jours,
        destination=destination,
        partner_name=partner_name,
        partner_contact=partner_contact,
        profil_voyageur=profil_voyageur,
        duree=duree,
        taille_groupe=taille_groupe,
        envies=envies,
        lines=lines,
    )


def generate_quote_pdf(quote: QuoteDocument, output_dir: Path | None = None) -> Path:
    out_dir = output_dir or OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(quote.devis_ref)
    path = out_dir / filename

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"Devis {quote.devis_ref}",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "QuoteTitle",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=BRAND_PRIMARY,
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "QuoteSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=BRAND_MUTED,
        spaceAfter=4,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=BRAND_PRIMARY,
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.black,
    )
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=8,
        textColor=BRAND_MUTED,
        leading=10,
    )

    story: list[Any] = []

    # En-tête agence (white label)
    story.append(Paragraph(quote.partner_name, title_style))
    if quote.partner_contact:
        story.append(Paragraph(quote.partner_contact, subtitle_style))
    story.append(Spacer(1, 0.3 * cm))

    # Bandeau titre
    header_data = [
        [
            Paragraph("<b>DEVIS — PROPOSITION D'ACTIVITÉS</b>", ParagraphStyle(
                "Hdr", parent=body_style, fontSize=14, textColor=colors.white,
            )),
            Paragraph(
                f"<b>{quote.devis_ref}</b>",
                ParagraphStyle("Ref", parent=body_style, fontSize=11, textColor=colors.white, alignment=TA_RIGHT),
            ),
        ]
    ]
    header_table = Table(header_data, colWidths=[12 * cm, 5 * cm])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_PRIMARY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.4 * cm))

    # Métadonnées voyage
    meta_rows = [
        ["Date d'émission", quote.date_emission.strftime("%d/%m/%Y")],
        ["Validité", f"{quote.validite_jours} jours (jusqu'au {quote.valid_until.strftime('%d/%m/%Y')})"],
        ["Destination", quote.destination],
        ["Profil voyageur", _profil_label(quote.profil_voyageur)],
    ]
    if quote.duree:
        meta_rows.append(["Durée du séjour", quote.duree])
    if quote.taille_groupe:
        meta_rows.append(["Taille du groupe", f"{quote.taille_groupe} personnes"])
    if quote.envies:
        meta_rows.append(["Centres d'intérêt", quote.envies.replace(",", ", ")])

    meta_table = Table(meta_rows, colWidths=[5 * cm, 12 * cm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), BRAND_MUTED),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.5 * cm))

    # Tableau activités
    story.append(Paragraph("Activités sélectionnées", section_style))
    table_header = ["Activité", "Durée", "Prix net", "Prix public"]
    table_data = [table_header]
    for line in quote.lines:
        titre = Paragraph(line.titre[:120], body_style)
        table_data.append([
            titre,
            line.duree[:30],
            _format_eur(line.prix_net),
            _format_eur(line.prix_public),
        ])

    table_data.append([
        Paragraph("<b>TOTAL</b>", body_style),
        "",
        Paragraph(f"<b>{_format_eur(quote.total_net)}</b>", body_style),
        Paragraph(f"<b>{_format_eur(quote.total_public)}</b>", body_style),
    ])

    activities_table = Table(table_data, colWidths=[9.5 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm])
    activities_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -2), 0.5, colors.lightgrey),
        ("LINEABOVE", (0, -1), (-1, -1), 1, BRAND_PRIMARY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(activities_table)
    story.append(Spacer(1, 0.4 * cm))

    # Conditions
    story.append(Paragraph("Conditions", section_style))
    conditions_text = (
        "• Prix nets agence (B2B) — hors hébergement, vols et assurances.<br/>"
        "• Disponibilité et horaires à confirmer à la réservation.<br/>"
        "• Annulation : selon conditions de chaque prestation (voir détail ci-dessous).<br/>"
        "• Ce devis est valable pour la durée indiquée ci-dessus."
    )
    story.append(Paragraph(conditions_text, body_style))

    cancel_lines = [ln for ln in quote.lines if ln.conditions_annulation.strip()]
    if cancel_lines:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("Conditions d'annulation par activité", section_style))
        for line in cancel_lines[:5]:
            snippet = line.conditions_annulation[:300]
            story.append(Paragraph(f"<b>{line.titre[:60]}</b> — {snippet}", footer_style))

    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(
        "<i>Catalogue d'activités fourni par Day Experience — document White Label à l'attention de votre client final.</i>",
        ParagraphStyle("Brand", parent=footer_style, alignment=TA_CENTER),
    ))

    doc.build(story)
    return path


def generate_quote_for_session(
    *,
    session_id: str,
    destination: str,
    activity_ids: list[str],
    devis_ref: str | None = None,
    validite_jours: int = 7,
) -> dict[str, str]:
    """Génère le PDF à partir des slots session + activités."""
    from memory.memory_manager import memory_manager

    slots = memory_manager.get_slots(session_id)
    if not devis_ref:
        from uuid import uuid4
        devis_ref = f"DEV-{date.today().strftime('%Y%m%d')}-{uuid4().hex[:4].upper()}"

    try:
        validite = int(str(slots.get("validite_jours", validite_jours) or validite_jours))
    except (TypeError, ValueError):
        validite = validite_jours

    quote = build_quote_document(
        devis_ref=devis_ref,
        destination=destination,
        activity_ids=activity_ids,
        partner_id=str(slots.get("partner_id", "") or "") or None,
        nom_agence=str(slots.get("nom_agence", "") or "") or None,
        profil_voyageur=str(slots.get("profil_voyageur", "") or ""),
        duree=str(slots.get("duree", "") or ""),
        taille_groupe=str(slots.get("taille_groupe", "") or ""),
        envies=str(slots.get("envies", "") or ""),
        validite_jours=validite,
    )
    pdf_path = generate_quote_pdf(quote)
    pdf_url = f"/quotes/{pdf_path.name}"

    memory_manager.update_slots(
        session_id,
        destination=destination,
        activites_selectionnees=activity_ids,
        devis_ref=devis_ref,
        validite_jours=str(validite),
    )

    return {
        "status": "ok",
        "devis_ref": devis_ref,
        "pdf_url": pdf_url,
        "pdf_path": str(pdf_path),
        "destination": destination,
        "activity_count": str(len(quote.lines)),
        "total_net": _format_eur(quote.total_net),
        "valid_until": quote.valid_until.strftime("%d/%m/%Y"),
    }
