"""
Client HTTP pour la plateforme B2B Day Experience.
Utilisé par le script de collecte scrape_b2b.py.
"""

from __future__ import annotations

import json
import logging
import math
import re
import string
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://b2b.day-experience.com"


@dataclass
class B2BConfig:
    login: str
    password: str
    agent_value: str = "1268|Mme Day Exeprience"
    base_url: str = BASE_URL
    request_delay: float = 0.35
    request_timeout: int = 90
    max_retries: int = 5
    retry_backoff: float = 2.0


@dataclass
class ActivityCard:
    id: str
    titre: str
    duree: str
    prix_public: str
    langues: str
    destination_id: int
    destination_nom: str


@dataclass
class ActivityDetail:
    id: str
    titre: str
    description: str
    prix_net: str
    prix_public: str
    duree: str
    langues: str
    inclusions: str
    conditions_annulation: str
    categorie: str


class B2BClient:
    def __init__(self, config: B2BConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "fr-FR,fr;q=0.9",
            }
        )
        self._logged_in = False

    def _url(self, path: str) -> str:
        return urljoin(self.config.base_url + "/", path.lstrip("/"))

    def _delay(self, extra: float = 0.0) -> None:
        wait = self.config.request_delay + extra
        if wait > 0:
            time.sleep(wait)

    def _reset_session(self) -> None:
        self.session.close()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "fr-FR,fr;q=0.9",
            }
        )
        self._logged_in = False

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        self.login()
        url = self._url(path)
        timeout = kwargs.pop("timeout", self.config.request_timeout)
        last_error: Exception | None = None

        for attempt in range(1, self.config.max_retries + 1):
            self._delay()
            try:
                response = self.session.request(method, url, timeout=timeout, **kwargs)
                response.raise_for_status()
                return response
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.ChunkedEncodingError,
            ) as exc:
                last_error = exc
                wait = self.config.retry_backoff ** attempt
                logger.warning(
                    "Requête %s %s — tentative %s/%s échouée (%s), nouvel essai dans %.1fs",
                    method,
                    path,
                    attempt,
                    self.config.max_retries,
                    type(exc).__name__,
                    wait,
                )
                self._reset_session()
                time.sleep(wait)

        assert last_error is not None
        raise last_error

    def login(self) -> None:
        if self._logged_in:
            return

        r = self.session.get(self._url("index.cfm"), timeout=60)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        form = soup.find("form", {"id": "submitFrm"})
        if not form:
            raise RuntimeError("Formulaire de connexion introuvable.")
        token_el = form.find("input", {"name": "crsf_token"})
        if not token_el:
            raise RuntimeError("Token CSRF de connexion introuvable.")

        self._delay()
        r = self.session.post(
            self._url("login.cfm"),
            data={
                "login": self.config.login,
                "password": self.config.password,
                "cmdValiderB2b": "1",
                "crsf_token": token_el["value"],
            },
            timeout=60,
        )
        r.raise_for_status()

        self._delay()
        r = self.session.post(
            self._url("index.cfm"),
            data={"idAgentPopup": self.config.agent_value, "AgentValider": "1"},
            timeout=60,
        )
        r.raise_for_status()
        self._logged_in = True
        logger.info("Connexion B2B et sélection agent OK.")

    def _get(self, path: str) -> str:
        return self._request("GET", path).text

    def _post(self, path: str, data: dict[str, Any]) -> str:
        return self._request("POST", path, data=data, timeout=max(self.config.request_timeout, 120)).text

    @staticmethod
    def _parse_search_json(raw: str) -> list[str]:
        body = raw.strip()
        if body.startswith("//"):
            body = body[2:]
        return json.loads(body)

    def discover_destinations(self) -> dict[int, str]:
        """Récupère les destinations depuis plusieurs pages + recherche alphabétique."""
        destinations: dict[int, str] = {}

        for path in ["index.cfm", "nos-destinations.cfm", "villeParPays.cfm?idPays=44"]:
            html = self._get(path)
            soup = BeautifulSoup(html, "html.parser")
            for link in soup.find_all("a", href=True):
                match = re.search(r"idVille=(\d+)", link["href"], re.I)
                if not match:
                    continue
                vid = int(match.group(1))
                name = re.sub(r"\d+\s*activit.*", "", link.get_text(" ", strip=True), flags=re.I).strip()
                name = BeautifulSoup(name, "html.parser").get_text(" ", strip=True)
                if name and len(name) < 80:
                    destinations[vid] = name

            for vid_str in re.findall(r"idVille=(\d+)", html, re.I):
                vid = int(vid_str)
                destinations.setdefault(vid, f"Ville-{vid}")

        for letter in string.ascii_lowercase:
            self._delay()
            raw = self.session.get(
                self._url(f"search.cfc?method=queryNames&returnformat=json&searchPhrase={letter}"),
                timeout=60,
            ).text
            try:
                items = self._parse_search_json(raw)
            except json.JSONDecodeError:
                continue
            for item in items:
                if "|" not in item:
                    continue
                label, meta = item.split("|", 1)
                parts = meta.split("_")
                if len(parts) < 5:
                    continue
                if parts[2] == "0" and parts[3] == "0" and parts[4] == "0" and parts[1].isdigit():
                    destinations[int(parts[1])] = label.strip()

        logger.info("Destinations découvertes : %s", len(destinations))
        return destinations

    def resolve_destination_name(self, destination_id: int) -> str:
        html = self._get(f"liste.cfm?idVille={destination_id}")
        soup = BeautifulSoup(html, "html.parser")
        hidden = soup.find("input", {"id": "nomVille"})
        if hidden and hidden.get("value"):
            return hidden["value"].strip()
        card = soup.select_one(".city-card-name, .hero-destination, h1")
        if card:
            text = card.get_text(" ", strip=True)
            if text:
                return text
        title = soup.title.string if soup.title and soup.title.string else ""
        match = re.search(r"Visitez\s+([^:]+):", title, re.I)
        if match:
            return match.group(1).strip()
        return f"Ville-{destination_id}"

    def _liste_form_values(self, id_ville: int) -> dict[str, str]:
        html = self._get(f"liste.cfm?idVille={id_ville}")
        soup = BeautifulSoup(html, "html.parser")

        def val(element_id: str, default: str = "") -> str:
            el = soup.find("input", {"id": element_id})
            return el["value"] if el and el.get("value") is not None else default

        return {
            "langue": val("filtreLangue"),
            "filtreOnglet": val("filtreOnglet"),
            "filtreLocalite": val("filtreLocalite"),
            "filtreTheme": val("filtreTheme"),
            "filtrePrix": val("filtrePrix"),
            "filtreTransfert": val("filtreTransfert"),
            "filtreLocDepart": val("filtreLocDepart"),
            "filtreLocArr": val("filtreLocArr"),
            "filtreTexteSearch": val("filtreTexteSearch"),
            "outcsrf": val("csrfctrl"),
        }

    @staticmethod
    def _parse_cards_html(html: str, destination_id: int, destination_nom: str) -> tuple[list[ActivityCard], int]:
        soup = BeautifulSoup(html, "html.parser")
        total_el = soup.find("input", {"id": "resTotalPrest"})
        total = int(total_el["value"]) if total_el and total_el.get("value") else 0
        cards: list[ActivityCard] = []

        for card in soup.select(".card"):
            aid = card.get("data-idproduit")
            if not aid:
                continue
            title_el = card.select_one(".card-title")
            duration_el = card.select_one(".card-duration")
            price_el = card.select_one(".card-price-num")
            langs = [img.get("alt", "") for img in card.select(".card-langs img")]
            cards.append(
                ActivityCard(
                    id=str(aid),
                    titre=title_el.get_text(strip=True) if title_el else "",
                    duree=duration_el.get_text(strip=True) if duration_el else "",
                    prix_public=price_el.get_text(strip=True) if price_el else "",
                    langues="|".join(filter(None, langs)),
                    destination_id=destination_id,
                    destination_nom=destination_nom,
                )
            )
        return cards, total

    def fetch_activities_for_destination(
        self, destination_id: int, destination_name: str, max_pages: int | None = None
    ) -> list[ActivityCard]:
        form_values = self._liste_form_values(destination_id)
        first_html = self._post(
            "ajax/ajaxListe.cfm",
            {
                **form_values,
                "page": 1,
                "idVille": destination_id,
                "filtreMot": "",
                "aprix": "agence",
            },
        )
        first_cards, total = self._parse_cards_html(first_html, destination_id, destination_name)
        if total == 0:
            return first_cards

        per_page = max(len(first_cards), 1)
        page_count = math.ceil(total / per_page)
        if max_pages is not None:
            page_count = min(page_count, max_pages)

        all_cards = {c.id: c for c in first_cards}
        for page in range(2, page_count + 1):
            html = self._post(
                "ajax/ajaxListe.cfm",
                {
                    **form_values,
                    "page": page,
                    "idVille": destination_id,
                    "filtreMot": "",
                    "aprix": "agence",
                },
            )
            cards, _ = self._parse_cards_html(html, destination_id, destination_name)
            for card in cards:
                all_cards[card.id] = card
            logger.info(
                "  %s (%s) page %s/%s — %s activités",
                destination_name,
                destination_id,
                page,
                page_count,
                len(all_cards),
            )

        return list(all_cards.values())

    def fetch_activity_detail(self, activity_id: str) -> ActivityDetail:
        html = self._get(f"produit.cfm?idActivity={activity_id}")
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else ""

        text = soup.get_text("\n", strip=True)
        prices = re.findall(r"(\d+[.,]\d+)\s*€", text)
        prix_net = ""
        for i, line in enumerate(text.split("\n")):
            if "tarif net" in line.lower() and i + 1 < len(text.split("\n")):
                m = re.search(r"(\d+[.,]\d+)", text.split("\n")[i + 1])
                if m:
                    prix_net = m.group(1).replace(",", ".")
                    break
        if not prix_net and prices:
            prix_net = prices[-1].replace(",", ".")

        meta = soup.find("meta", {"name": "description"})
        description = (meta.get("content") or "").strip() if meta else ""
        if not description:
            for sel in ["#tab_description", ".product-description", "[class*='description']"]:
                el = soup.select_one(sel)
                if el and len(el.get_text(strip=True)) > 40:
                    description = el.get_text(" ", strip=True)[:2000]
                    break

        duree = ""
        langues = ""
        inclusions = ""
        annulation = ""
        categorie = ""

        for section in soup.select(".panel, .tab-pane, section, .bloc"):
            heading = section.find(["h2", "h3", "h4", "strong"])
            if not heading:
                continue
            label = heading.get_text(" ", strip=True).lower()
            body = section.get_text(" ", strip=True)
            if "durée" in label or "duree" in label:
                duree = body[:200]
            elif "langue" in label:
                langues = body[:200]
            elif "inclus" in label:
                inclusions = body[:500]
            elif "annul" in label:
                annulation = body[:500]

        if not duree:
            m = re.search(r"Durée[^\n]*\n([^\n]+)", text, re.I)
            if m:
                duree = m.group(1).strip()

        public_match = re.search(r"(\d+[.,]?\d*)\s*€", text)
        prix_public = public_match.group(1).replace(",", ".") if public_match else ""

        return ActivityDetail(
            id=activity_id,
            titre=title,
            description=description,
            prix_net=prix_net,
            prix_public=prix_public,
            duree=duree,
            langues=langues,
            inclusions=inclusions,
            conditions_annulation=annulation,
            categorie=categorie,
        )

    def fetch_faq(self) -> list[dict[str, str]]:
        html = self._get("faq.cfm")
        soup = BeautifulSoup(html, "html.parser")
        rows: list[dict[str, str]] = []
        categorie = "General"

        for group in soup.select(".faq-group"):
            label_el = group.select_one(".faq-group-label")
            if label_el:
                categorie = label_el.get_text(strip=True)

            for item in group.select(".faq-item"):
                q_el = item.select_one(".faq-q-text")
                a_el = item.select_one(".faq-answer-inner")
                if not q_el or not a_el:
                    continue
                rows.append(
                    {
                        "question": q_el.get_text(" ", strip=True),
                        "reponse": a_el.get_text(" ", strip=True),
                        "categorie": categorie,
                    }
                )
        logger.info("FAQ : %s entrées", len(rows))
        return rows

    def fetch_orders(self) -> list[dict[str, str]]:
        html = self._get("mes-dossiers.cfm")
        soup = BeautifulSoup(html, "html.parser")
        rows: list[dict[str, str]] = []

        for table in soup.find_all("table"):
            headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
            if not headers:
                continue
            for tr in table.find_all("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
                if len(cells) < 2:
                    continue
                row = dict(zip(headers, cells, strict=False))
                if any(row.values()):
                    rows.append(row)

        logger.info("Commandes / dossiers : %s lignes", len(rows))
        return rows

    @staticmethod
    def infer_profil(titre: str, categorie: str) -> str:
        t = f"{titre} {categorie}".lower()
        if any(w in t for w in ["famille", "enfant", "kids"]):
            return "famille"
        if any(w in t for w in ["couple", "romant", "cruise", "croisière", "croisiere"]):
            return "couple"
        if any(w in t for w in ["groupe", "team"]):
            return "groupe"
        if any(w in t for w in ["solo", "privé", "prive", "private"]):
            return "solo"
        return "general"
