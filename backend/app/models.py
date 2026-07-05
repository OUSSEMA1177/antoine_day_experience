"""Pydantic models for API requests and responses."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "day-experience-ai"


class ActivityOut(BaseModel):
    id: str
    destination_id: str = ""
    titre: str = ""
    description: str = ""
    prix: str = ""
    prix_public: str = ""
    duree: str = ""
    langues: str = ""
    inclusions: str = ""
    categorie: str = ""
    profil_cible: str = ""
    horaires: str = ""
    conditions_annulation: str = ""


class ActivitiesResponse(BaseModel):
    total: int
    items: list[ActivityOut]


class DestinationOut(BaseModel):
    id: str
    nom: str = ""
    pays: str = ""
    region: str = ""
    description: str = ""
    saison_ideale: str = ""


class DestinationsResponse(BaseModel):
    total: int
    items: list[DestinationOut]


class OrderOut(BaseModel):
    id: str = ""
    reference: str = ""
    partner_id: str = ""
    statut: str = ""
    date: str = ""
    activites: str = ""
    montant: str = ""


class PartnerOut(BaseModel):
    id: str
    nom_agence: str = ""
    pays: str = ""
    greeting_message: str = ""


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Identifiant de session utilisateur")
    message: str = Field(..., min_length=1, description="Message de l'utilisateur")
    partner_id: str | None = Field(
        default=None,
        description="Identifiant agence partenaire B2B (white label devis)",
    )


class ActivityPreview(BaseModel):
    id: str
    titre: str
    prix_net: str = ""
    duree: str = ""


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    tools_used: list[str] = Field(default_factory=list)
    quote_url: str | None = Field(default=None, description="URL du devis PDF si généré")
    devis_ref: str | None = Field(default=None, description="Référence du devis")
    quote_ready: bool = Field(default=False, description="Bouton devis activable")
    quote_activities: list[ActivityPreview] = Field(default_factory=list)
    destination: str | None = None
    nom_agence: str | None = None


class QuoteRequest(BaseModel):
    session_id: str = Field(..., description="Session conversationnelle")
    destination: str = Field(..., min_length=1)
    activity_ids: list[str] = Field(..., min_length=1)
    partner_id: str | None = None
    devis_ref: str | None = None
    validite_jours: int = Field(default=7, ge=1, le=90)


class QuoteResponse(BaseModel):
    session_id: str
    devis_ref: str
    pdf_url: str
    destination: str
    activity_count: int
    total_net: str
    valid_until: str


class QuoteSessionRequest(BaseModel):
    session_id: str
    partner_id: str | None = None


class QuoteStateResponse(BaseModel):
    session_id: str
    quote_ready: bool
    missing: list[str] = Field(default_factory=list)
    destination: str | None = None
    nom_agence: str | None = None
    activities: list[ActivityPreview] = Field(default_factory=list)
