"""Tests golden : rejoue les transcripts réels qui ont cassé (0 token attendu).

Chaque test reproduit mot pour mot une conversation utilisateur ayant révélé
des bugs de routage, et verrouille le comportement corrigé tour par tour.
"""

from unittest.mock import MagicMock, patch

from agent.orchestrator import orchestrator
from memory.conversation_manager import conversation_manager
from memory.memory_manager import memory_manager
from memory.session_store import session_store
from services.data_loader import data_loader


def _mock_settings():
    return MagicMock(
        llm_model="anthropic/claude-haiku-4-5",
        anthropic_api_key="test-key",
        groq_api_key="",
        gemini_api_key="",
        llm_fallback_model="",
        llm_max_tokens=512,
        llm_timeout=90,
        llm_retry_max=0,
        llm_retry_delay=0.1,
        llm_nlu_extract=True,
        llm_log_usage=False,
        llm_history_limit=8,
        llm_catalog_inject_limit=4,
        llm_compact_prompt=True,
        support_email="support@test.com",
    )


@patch("agent.orchestrator.get_settings")
def test_golden_afrique_du_sud_transcript(mock_settings) -> None:
    """Transcript Afrique du Sud : j ai pas aime / autre option / typos pays."""
    mock_settings.return_value = _mock_settings()
    session = "golden-afrique-sud"
    session_store.clear(session)

    with patch("litellm.completion") as mock_llm:
        # Tour 1 — pays catalogue mono-ville
        reply, _, _ = orchestrator.chat(session, "Afrique du Sud")
        assert "Parc Kruger" in reply
        assert "Le Caire" not in reply  # pas la liste continent

        # Tour 2 — confirmation ville → liste numérotée
        reply, _, _ = orchestrator.chat(session, "oui")
        assert "1." in reply and "2." in reply
        assert memory_manager.get_slots(session).get("destination") == "Parc Kruger"

        # Tour 3 — rejet de la liste ≠ « sélection vide »
        reply, _, _ = orchestrator.chat(session, "j ai pas aime")
        assert "ne reste plus" not in reply.casefold()
        assert "il ne reste" not in reply.casefold()
        # nouvelles options ou vérité catalogue, jamais un message de sélection vide
        assert "autres options" in reply.casefold() or "1." in reply

        # Tour 4 — « autre option » ≠ demande de thématique pour ajout
        reply, _, _ = orchestrator.chat(session, "autre option")
        assert "thématique pour l'activité supplémentaire" not in reply.casefold()

        # Tour 5 — typo pays → réponse pays, pas continent
        reply, _, _ = orchestrator.chat(
            session, "dans l afrique de sud vous avez juste Parc Kruger ??"
        )
        assert "Parc Kruger" in reply
        assert "Le Caire" not in reply
        assert "Marrakech" not in reply

        # Tour 6 — autre typo pays → toujours pays, pas continent
        reply, _, _ = orchestrator.chat(session, "et l afrique de sude ???")
        assert "Parc Kruger" in reply
        assert "Le Caire" not in reply

        # Toute la conversation doit rester à 0 token
        mock_llm.assert_not_called()

    # La destination n'a jamais été détruite
    assert memory_manager.get_slots(session).get("destination") == "Parc Kruger"


@patch("agent.orchestrator.get_settings")
def test_golden_tokyo_les_trois_premiers_ouii(mock_settings) -> None:
    """Transcript Tokyo : les 3 premiers → ouii → devis à 3 activités, pas 4."""
    from memory.quote_state import _parse_id_list

    mock_settings.return_value = _mock_settings()
    session = "golden-tokyo"
    session_store.clear(session)

    ids = ["54782", "41555", "72738", "51876"]
    titles = [data_loader.get_activity_by_id(i)["titre"] for i in ids]
    assert all(titles)
    memory_manager.update_slots(
        session,
        destination="Tokyo",
        profil_voyageur="couple",
        partner_id="1",
        nom_agence="Test Agence",
        activites_proposees=",".join(ids),
        activites_discutees=",".join(ids),
    )
    lines = "\n".join(
        f"{n}. **{t}** — {50 * n} € (net)" for n, t in enumerate(titles, 1)
    )
    conversation_manager.add_turn(session, "activites a tokyo", lines)

    with patch("litellm.completion") as mock_llm:
        # Tour 1 — sélection des 3 premiers, pas d'auto-remplissage à 4
        reply, _, meta = orchestrator.chat(session, "les 3 premiers")
        slots = memory_manager.get_slots(session)
        assert _parse_id_list(slots.get("activites_selectionnees")) == ids[:3]
        assert slots.get("awaiting_quote_confirm") == "1"
        assert meta.get("quote_ready") is False

        # Tour 2 — « ouii » = confirmation devis, jamais un lieu inconnu
        reply, _, meta = orchestrator.chat(session, "ouii")
        slots = memory_manager.get_slots(session)
        assert slots.get("destination") == "Tokyo"
        assert "pas disponible" not in reply.casefold()
        assert "devis" in reply.casefold()
        assert meta.get("quote_ready") is True
        assert len(meta.get("quote_activities") or []) == 3
        assert _parse_id_list(slots.get("activites_selectionnees")) == ids[:3]

        # Tour 3 — « le devis » post-devis → régénère avec la même sélection
        reply, _, meta = orchestrator.chat(session, "le devis")
        assert meta.get("quote_ready") is True
        assert len(meta.get("quote_activities") or []) == 3
        assert memory_manager.get_slots(session).get("destination") == "Tokyo"

        mock_llm.assert_not_called()
