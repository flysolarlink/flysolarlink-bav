# -*- coding: utf-8 -*-
"""
FlySolarLink BAV Generator — Application principale
Backend Flask : récupération données + génération PDF
"""
from flask import Flask, render_template, request, jsonify, send_file
import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime, timezone
from io import BytesIO
import traceback

# PDF generation
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

app = Flask(__name__)

# ── Constantes ───────────────────────────────────────────────
SKEYES_UAS_ZONES = "https://api-cis.skeyes.be/public/uas-zones"
NOAA_KP          = "https://services.swpc.noaa.gov/text/3-day-forecast.txt"

DRONES = {
    "mavic3_c1":   {"nom": "DJI Mavic 3",          "classe": "C1", "mtow": 895,  "remote_id": True},
    "mini4pro_c0": {"nom": "DJI Mini 4 Pro",        "classe": "C0", "mtow": 249,  "remote_id": True},
    "mini5pro":    {"nom": "DJI Mini 5 Pro",         "classe": "C0", "mtow": 249,  "remote_id": True},
    "matrice4t":   {"nom": "DJI Matrice 4T",         "classe": "C2", "mtow": 1195, "remote_id": True},
    "matrice4e":   {"nom": "DJI Matrice 4E",         "classe": "C2", "mtow": 1195, "remote_id": True},
    "matrice400":  {"nom": "DJI Matrice 400 RTK",    "classe": "C3", "mtow": 9700, "remote_id": True},
}

# ═══════════════════════════════════════════════════════════
#  ROUTES PRINCIPALES
# ═══════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html", drones=DRONES)

@app.route("/api/meteo", methods=["POST"])
def get_meteo():
    """Récupère IRM + METAR/TAF pour une ville."""
    data = request.json
    ville = data.get("ville", "liege").lower().replace(" ", "-").replace("é","e").replace("è","e")
    try:
        # IRM bulletin
        irm_url = f"https://www.meteo.be/fr/{ville}"
        r = requests.get(irm_url, timeout=8,
                         headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        # Chercher le bulletin
        bulletin = ""
        for tag in soup.find_all(["p", "div"]):
            txt = tag.get_text(strip=True)
            if len(txt) > 80 and any(w in txt.lower() for w in
               ["vent","nuage","pluie","averse","soleil","temp","sec","couvert"]):
                bulletin = txt[:500]
                break

        # Précipitations horaires
        precip_text = r.text
        precip_matches = re.findall(r'(\d{1,2})h(\d+)%', precip_text)
        precip = {f"{h}h": f"{p}%" for h, p in precip_matches[:24]}

        # METAR/TAF EBLG
        metar_url = "https://fr.allmetsat.com/metar-taf/pays-bas-belgique-luxembourg.php?icao=EBLG"
        r2 = requests.get(metar_url, timeout=8,
                          headers={"User-Agent": "Mozilla/5.0"})
        metar_raw = ""
        taf_raw   = ""
        metar_match = re.search(r'(METAR|SPECI):\s*(EBLG\s+\S+.*?)(?=\n|TAF|$)', r2.text)
        taf_match   = re.search(r'TAF:\s*(EBLG\s+\S+.*?)(?=\n\n|\Z)', r2.text, re.DOTALL)
        if metar_match:
            metar_raw = metar_match.group(2).strip()[:200]
        if taf_match:
            taf_raw = taf_match.group(1).strip()[:400]

        return jsonify({
            "ok": True,
            "ville": ville,
            "irm_url": irm_url,
            "bulletin": bulletin or "Bulletin IRM disponible sur meteo.be",
            "precip": precip,
            "metar": metar_raw or "METAR non disponible — consulter allmetsat.com",
            "taf":   taf_raw   or "TAF non disponible — consulter allmetsat.com",
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/kp", methods=["GET"])
def get_kp():
    """Récupère le forecast KP NOAA SWPC."""
    try:
        r = requests.get(NOAA_KP, timeout=8)
        txt = r.text
        # Parser les lignes KP
        kp_data = {}
        in_table = False
        issued = ""
        for line in txt.split("\n"):
            if ":Issued:" in line:
                issued = line.replace(":Issued:", "").strip()
            if "00-03UT" in line:
                in_table = True
            if in_table and re.match(r'\d{2}-\d{2}UT', line.strip()):
                parts = line.strip().split()
                if len(parts) >= 2:
                    slot = parts[0]
                    vals = parts[1:]
                    kp_data[slot] = vals
            if in_table and line.strip() == "":
                break

        # KP du jour J (colonne 0) et J+1
        kp_today = {}
        kp_j1    = {}
        for slot, vals in kp_data.items():
            if len(vals) >= 1:
                kp_today[slot] = vals[0]
            if len(vals) >= 2:
                kp_j1[slot]    = vals[1]

        # KP max du jour
        try:
            max_kp = max(float(v.split("(")[0]) for v in kp_today.values() if v)
        except:
            max_kp = 0

        niveau = "calme"
        couleur = "green"
        if max_kp >= 5:
            niveau = "tempête géomagnétique ⚠"
            couleur = "red"
        elif max_kp >= 4:
            niveau = "agité — GPS perturbé"
            couleur = "orange"
        elif max_kp >= 3:
            niveau = "légèrement agité"
            couleur = "yellow"

        return jsonify({
            "ok": True,
            "issued": issued,
            "kp_today": kp_today,
            "kp_j1": kp_j1,
            "max_kp": max_kp,
            "niveau": niveau,
            "couleur": couleur,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/geozones", methods=["POST"])
def get_geozones():
    """
    Appel skeyes Public API /uas-zones.
    L'appel est fait depuis le SERVEUR (pas le navigateur).
    """
    data = request.json
    params = {}
    vol_datetime = data.get("vol_datetime")
    if vol_datetime:
        params["start_datetime"] = vol_datetime
    try:
        r = requests.get(
            SKEYES_UAS_ZONES,
            params=params,
            timeout=10,
            headers={"Accept": "application/json",
                     "User-Agent": "FlySolarLink-BAVGenerator/1.0"}
        )
        if r.status_code == 200:
            zones_data = r.json()
            # Filtrer par proximité GPS si coords fournies
            lat = data.get("lat")
            lon = data.get("lon")
            zones = zones_data.get("items", [])
            if lat and lon:
                zones = filter_zones_by_coords(zones, float(lat), float(lon), radius_km=5)
            # Analyser les zones
            analyse = analyser_zones(zones)
            return jsonify({"ok": True, "zones": zones, "analyse": analyse})
        else:
            return jsonify({
                "ok": False,
                "error": f"API skeyes HTTP {r.status_code}",
                "fallback": True,
                "message": "Vérifier manuellement sur map.droneguide.be"
            })
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e),
            "fallback": True,
            "message": "Vérifier manuellement sur map.droneguide.be"
        })


def filter_zones_by_coords(zones, lat, lon, radius_km=5):
    """Filtre les zones géographiquement proches."""
    import math
    result = []
    for item in zones:
        zone = item.get("zone", {})
        for geom in zone.get("geometry", []):
            proj = geom.get("horizontalProjection", {})
            center = proj.get("center")
            if center and len(center) == 2:
                z_lon, z_lat = center
                dist = math.sqrt((z_lat - lat)**2 + (z_lon - lon)**2) * 111
                if dist <= radius_km:
                    result.append(item)
                    break
    return result


def analyser_zones(zones):
    """Analyse les zones et retourne un résumé structuré."""
    analyse = {
        "nb_zones": len(zones),
        "zones_actives": [],
        "zones_bientot": [],
        "zones_inactives": [],
        "autorisation_requise": False,
        "delai_max_jours": 0,
        "daa_requis": False,
        "remote_id_requis": False,
        "altitude_max_m": None,
        "alerte": "",
    }
    for item in zones:
        zone   = item.get("zone", {})
        status = item.get("status", "UNKNOWN")
        nom    = zone.get("name", zone.get("identifier", "Zone inconnue"))
        restriction = zone.get("restriction", "")
        conditions  = zone.get("restrictionConditions", [])
        authorities = zone.get("zoneAuthority", [])

        zone_info = {
            "nom":         nom,
            "status":      status,
            "restriction": restriction,
            "conditions":  conditions,
            "contacts":    [],
            "delai_j":     0,
        }

        # Contacts
        for auth in authorities:
            contact = {}
            if auth.get("email"):   contact["email"] = auth["email"]
            if auth.get("phone"):   contact["tel"]   = auth["phone"]
            if auth.get("name"):    contact["nom"]   = auth["name"]
            if auth.get("intervalBefore"):
                ib = auth["intervalBefore"]
                # Parser ISO 8601 duration ex: P5D, P4DT20S
                days_match = re.search(r'P(\d+)D', ib)
                if days_match:
                    zone_info["delai_j"] = int(days_match.group(1))
                    analyse["delai_max_jours"] = max(
                        analyse["delai_max_jours"], zone_info["delai_j"])
            zone_info["contacts"].append(contact)

        # Vérifier conditions spéciales
        cond_str = " ".join(conditions).lower()
        if "daa" in cond_str or "notification" in cond_str or "3 h" in cond_str or "3h" in cond_str:
            analyse["daa_requis"] = True
        if "remote id" in cond_str or "identification" in cond_str:
            analyse["remote_id_requis"] = True

        # Altitude
        for geom in zone.get("geometry", []):
            upper = geom.get("upperLimit")
            ref   = geom.get("upperVerticalReference", "")
            if upper and "AGL" in ref:
                if analyse["altitude_max_m"] is None or upper < analyse["altitude_max_m"]:
                    analyse["altitude_max_m"] = upper

        if restriction in ["PROHIBITED", "REQ_AUTHORISATION"]:
            analyse["autorisation_requise"] = True

        # Trier par status
        if status == "ACTIVE":
            analyse["zones_actives"].append(zone_info)
        elif status == "SOON":
            analyse["zones_bientot"].append(zone_info)
        else:
            analyse["zones_inactives"].append(zone_info)

    # Alerte globale
    if analyse["delai_max_jours"] >= 5:
        analyse["alerte"] = f"⚠ DÉLAI {analyse['delai_max_jours']} JOURS OUVRABLES — Demande d'autorisation obligatoire à l'avance !"
    elif analyse["autorisation_requise"]:
        analyse["alerte"] = "⚠ Autorisation requise pour une ou plusieurs zones"
    elif analyse["daa_requis"]:
        analyse["alerte"] = "ℹ Notification DAA requise ≥3h avant le vol"

    return analyse


@app.route("/api/generate_pdf", methods=["POST"])
def generate_pdf():
    """Génère le PDF du BAV complet."""
    try:
        data = request.json
        pdf_buffer = build_bav_pdf(data)
        date_str = data.get("date_vol", "").replace("/", "").replace("-", "")
        lieu_str = data.get("lieu", "vol").replace(" ", "_")[:20]
        filename = f"BAV_FlySolarLink_{lieu_str}_{date_str}.pdf"
        pdf_buffer.seek(0)
        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════════════════
#  GÉNÉRATION PDF
# ═══════════════════════════════════════════════════════════

def build_bav_pdf(d):
    """Construit le PDF BAV à partir des données collectées."""
    W, H = A4
    M    = 15*mm
    BODY = W - 2*M

    NAVY  = colors.HexColor("#0d1f3c")
    CYAN  = colors.HexColor("#4dc8e8")
    WARN  = colors.HexColor("#cc3300")
    WHITE = colors.white
    LG    = colors.HexColor("#f0f4f8")
    MG    = colors.HexColor("#dde3ec")
    BG2   = colors.HexColor("#e8f0fb")
    OK    = colors.HexColor("#e8f7e8")
    OKBRD = colors.HexColor("#1a7a1a")
    WBKG  = colors.HexColor("#fff0f0")

    def ps(name, **kw):
        base = dict(fontName="Helvetica", fontSize=8.5, leading=12,
                    textColor=colors.black, spaceAfter=0, spaceBefore=0)
        base.update(kw)
        return ParagraphStyle(name, **base)

    TITLE  = ps("T",  fontName="Helvetica-Bold", fontSize=14, textColor=WHITE, alignment=TA_CENTER)
    DATER  = ps("D",  fontName="Helvetica-Bold", fontSize=11, textColor=CYAN,  alignment=TA_RIGHT)
    BRAND  = ps("B",  fontName="Helvetica-Bold", fontSize=11, textColor=CYAN)
    SHDR   = ps("SH", fontName="Helvetica-Bold", fontSize=8.5, textColor=WHITE)
    LBL    = ps("L",  fontName="Helvetica-Bold", fontSize=8,  textColor=NAVY, leading=11)
    VAL    = ps("V",  fontSize=8.5, leading=12)
    CODE   = ps("C",  fontName="Courier", fontSize=8, leading=11, textColor=NAVY)
    SRC    = ps("S",  fontName="Helvetica-Oblique", fontSize=6.8,
                textColor=colors.HexColor("#6677aa"), leading=10)
    OKST   = ps("OK", fontName="Helvetica-Bold", fontSize=8.5, textColor=OKBRD)
    WARNST = ps("W",  fontName="Helvetica-Bold", fontSize=8.5, textColor=WARN)
    FOOT   = ps("F",  fontSize=7, textColor=colors.HexColor("#778899"),
                alignment=TA_CENTER, leading=10)

    def hdr(text):
        t = Table([[Paragraph(text, SHDR)]], colWidths=[BODY])
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),NAVY),
            ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
            ("LEFTPADDING",(0,0),(-1,-1),7),
        ]))
        return t

    def row(label, value, source=None, bg=LG):
        inner = [Paragraph(label, LBL), Paragraph(value, VAL)]
        if source:
            inner.append(Paragraph(source, SRC))
        t = Table([[inner]], colWidths=[BODY])
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),bg),
            ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
            ("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),
        ]))
        return t

    def div():
        t = Table([[""]], colWidths=[BODY])
        t.setStyle(TableStyle([
            ("LINEBELOW",(0,0),(-1,-1),0.4,MG),
            ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0),
        ]))
        return t

    def chk(checked, label, source=None):
        mark = "■" if checked else "□"
        inner = [Paragraph(f'<font face="Helvetica-Bold">{mark}</font>  {label}', VAL)]
        if source:
            inner.append(Paragraph(source, SRC))
        t = Table([[inner]], colWidths=[BODY])
        t.setStyle(TableStyle([
            ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3),
            ("LEFTPADDING",(0,0),(-1,-1),10),
        ]))
        return t

    def banner(text, style, bg, brd):
        t = Table([[Paragraph(text, style)]], colWidths=[BODY])
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),bg),
            ("LEFTPADDING",(0,0),(-1,-1),10),
            ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
            ("BOX",(0,0),(-1,-1),1.2,brd),
        ]))
        return t

    story = []
    sp = lambda n=2: story.append(Spacer(1, n*mm))

    # Données
    date_vol    = d.get("date_vol", "")
    heure_vol   = d.get("heure_vol", "")
    lieu        = d.get("lieu", "")
    adresse     = d.get("adresse", "")
    coords      = d.get("coords", "")
    objectif    = d.get("objectif", "Entraînement au pilotage")
    drone_key   = d.get("drone", "mavic3_c1")
    drone_info  = DRONES.get(drone_key, DRONES["mavic3_c1"])
    instructeur = d.get("instructeur", True)
    meteo       = d.get("meteo", {})
    kp_data     = d.get("kp", {})
    zones_data  = d.get("zones", {})
    analyse     = d.get("analyse", {})
    generated   = datetime.now().strftime("%d/%m/%Y %H:%M")

    # ── EN-TÊTE
    top = Table([[
        Paragraph("FlySolarLink", BRAND),
        Paragraph("BRIEFING AVANT VOL", TITLE),
        Paragraph(date_vol, DATER),
    ]], colWidths=[38*mm, BODY-76*mm, 38*mm])
    top.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),NAVY),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
        ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
    ]))
    story.append(top)
    story.append(Paragraph(
        f"flysolarlink.com — contact@flysolarlink.com — Généré le {generated}",
        ps("web", fontSize=7, textColor=colors.HexColor("#8899bb"), alignment=TA_CENTER)))
    sp(3)

    # ── 1. MISSION
    story.append(hdr("Objectif des opérations"))
    sp(0.5)
    story.append(row("Objectif", objectif, "Source : planification interne FlySolarLink"))
    story.append(div())
    story.append(row("Machine utilisée",
        f"{drone_info['nom']} — Classe {drone_info['classe']} — "
        f"Remote ID {'intégré actif' if drone_info['remote_id'] else 'non requis'} — "
        f"MTOW ~{drone_info['mtow']} g",
        f"Source : flotte FlySolarLink — dji.com", bg=BG2))
    story.append(div())
    story.append(row("Zone géographique",
        f"{lieu}\n{adresse}\n{coords}",
        "Source : planification interne FlySolarLink"))
    story.append(div())
    story.append(row("Heure de vol",
        f"{date_vol} — {heure_vol} heure locale CEST",
        "Source : planification interne FlySolarLink", bg=BG2))
    sp(2)

    # ── 2. TYPE DE VOL
    story.append(hdr("Type de vol"))
    sp(0.5)
    story.append(row("Catégorie",
        "Open  <b><u>A1/A2</u></b> / <strike>A3</strike>  —  "
        "<strike>STS</strike>  —  <strike>Specific avec autorisation de vol</strike>  →  <b>Open A2</b>",
        "Source : EU 2019/947 — Règlement 2019/945"))
    sp(1)

    # ── 3. DOCUMENTS
    story.append(hdr("Documents disponibles : Assurance, preuves de compétence, autorisations…"))
    sp(0.5)
    for ok, txt, src in [
        (True,  "Assurance RC Pro en ordre",     "Source : police RC Pro FlySolarLink"),
        (True,  "Certificat A2 CofC",            "Source : certificat BCAA / DGAC pilote"),
        (True,  "Enregistrement opérateur DGTA", "Source : DGTA — dgta.fgov.be"),
    ]:
        story.append(chk(ok, txt, src))
    sp(2)

    # ── 4. GÉOZONES
    story.append(hdr("Zone de vol — Analyse Géozones skeyes Public API"))
    sp(0.5)

    alerte_geo = analyse.get("alerte", "")
    nb_zones   = analyse.get("nb_zones", 0)
    zones_act  = analyse.get("zones_actives", [])
    daa_req    = analyse.get("daa_requis", False)
    remote_req = analyse.get("remote_id_requis", False)
    alt_max    = analyse.get("altitude_max_m")
    delai      = analyse.get("delai_max_jours", 0)

    if zones_data.get("ok") and nb_zones > 0:
        story.append(row("Géozones détectées dans le rayon de 5 km",
            f"{nb_zones} zone(s) identifiée(s) via skeyes Public API /uas-zones",
            "Source : api-cis.skeyes.be/public/uas-zones — données temps réel"))

        for z in zones_act[:5]:
            bg_z = WBKG if z.get("delai_j", 0) >= 5 else BG2
            contacts_str = " | ".join([
                f"{c.get('nom','')} {c.get('email','')} {c.get('tel','')}".strip()
                for c in z.get("contacts", [])
            ])
            delai_str = f" — ⚠ Délai : {z['delai_j']} jours ouvrables" if z.get("delai_j") else ""
            story.append(div())
            story.append(row(
                f"Zone : {z['nom']}  [{z['status']}]",
                f"Restriction : {z['restriction']}\n"
                f"Conditions : {', '.join(z['conditions'][:3]) if z['conditions'] else 'Voir droneguide'}"
                f"{delai_str}\n"
                f"Contact : {contacts_str or 'Voir map.droneguide.be'}",
                "Source : skeyes Public API — temps réel",
                bg=bg_z))

        # Altitude
        if alt_max:
            story.append(div())
            story.append(row("⚠ Altitude maximale VLL/héliport",
                f"Limite spécifique détectée : {alt_max} m AGL\n"
                f"Cette limite s'applique et prime sur la limite Open A2 standard (120 m)",
                "Source : skeyes Public API — geometry.upperLimit", bg=WBKG))

        if alerte_geo:
            sp(0.5)
            is_warn = "⚠" in alerte_geo
            story.append(banner(alerte_geo,
                WARNST if is_warn else OKST,
                WBKG if is_warn else OK,
                WARN if is_warn else OKBRD))
    else:
        # Fallback manuel
        story.append(banner(
            "⚠ API skeyes non disponible — Vérification manuelle obligatoire :\n"
            "→ map.droneguide.be : zoomer sur la zone et cliquer chaque zone colorée\n"
            "→ AIP ENR 5.1 (ops.skeyes.be) : vérifier zones militaires et horaires\n"
            "→ skeyes.be NOTAMs : vérifier NOTAMs actifs sur la zone",
            WARNST, WBKG, WARN))

    story.append(div())
    story.append(row("Obstacles",
        "À évaluer sur site : arbres, lignes HT, structures bâties.\n"
        "Périmètre de sécurité à établir avant décollage.",
        "Source : EU 2019/947 — inspection visuelle obligatoire"))
    story.append(div())
    story.append(row("Dangers électromagnétiques",
        "À vérifier sur site avant décollage. Tester GPS et compas.",
        "Source : planification interne", bg=BG2))
    sp(2)

    # ── 5. AIP & NOTAM
    story.append(hdr("AIP et NOTAMs"))
    sp(0.5)
    story.append(row("FIR / Espace aérien",
        "Bruxelles FIR — AIP consulté via skeyes.be.",
        "Source : AIP Belgique — ops.skeyes.be"))
    story.append(div())
    story.append(row("NOTAMs",
        f"⚠ Vérifier obligatoirement sur skeyes.be le matin du {date_vol} avant le vol.",
        "Source : skeyes.be → NOTAMs Belgique", bg=BG2))
    sp(2)

    # ── 6. MÉTÉO
    story.append(hdr("Météo"))
    sp(0.5)
    story.append(row("Image radar",
        f"Consulter radar IRM le matin : meteo.be → Météo → Observations → Radar",
        "Source : IRM — meteo.be/fr/meteo/observations/radar"))
    story.append(div())

    if meteo.get("ok") and meteo.get("bulletin"):
        story.append(row(f"Bulletin IRM {meteo.get('ville','').capitalize()}",
            meteo["bulletin"][:400],
            f"Source : IRM {meteo.get('irm_url','')} — données temps réel", bg=BG2))
        story.append(div())

    metar_val = meteo.get("metar", "À actualiser le matin du vol sur allmetsat.com")
    taf_val   = meteo.get("taf",   "À actualiser le matin du vol sur allmetsat.com")

    story.append(row("METAR EBLG (allmetsat.com — 'Liège TAF')",
        "Dernière observation disponible :",
        "Source : allmetsat.com — EBLG — données en temps réel"))
    story.append(Table([[Paragraph(metar_val, CODE)]], colWidths=[BODY]))
    story.append(div())
    story.append(row("TAF EBLG",
        "Dernière prévision disponible :",
        "Source : allmetsat.com — TAF EBLG", bg=BG2))
    story.append(Table([[Paragraph(taf_val, CODE)]], colWidths=[BODY]))
    sp(2)

    # ── 7. KP
    story.append(hdr("Indice KP"))
    sp(0.5)
    if kp_data.get("ok"):
        max_kp = kp_data.get("max_kp", 0)
        niveau = kp_data.get("niveau", "")
        issued = kp_data.get("issued", "")
        kp_today = kp_data.get("kp_today", {})
        kp_str = "  |  ".join([f"{k}: {v}" for k, v in list(kp_today.items())[:8]])
        is_ok = max_kp < 4
        story.append(row("Forecast KP — NOAA SWPC",
            f"KP max prévu : {max_kp} — {niveau}\n{kp_str}",
            f"Source : NOAA SWPC — services.swpc.noaa.gov — {issued}"))
        sp(0.5)
        story.append(banner(
            f"{'✔' if is_ok else '⚠'}  KP max = {max_kp} — {niveau.upper()}",
            OKST if is_ok else WARNST,
            OK   if is_ok else WBKG,
            OKBRD if is_ok else WARN))
    else:
        story.append(row("Indice KP",
            "À vérifier le matin du vol sur spaceweatherlive.com\n"
            "KP ≤ 3 = calme ✔  |  KP 4-5 = vigilance  |  KP ≥ 5 = reporter",
            "Source : spaceweatherlive.com — NOAA SWPC"))
    sp(2)

    # ── 8. BRIEFING OPS
    story.append(hdr("Briefing aux personnes impliquées dans les opérations"))
    sp(0.5)
    story.append(row("Briefing réalisé",
        "OUI — instructeur présent sur site" if instructeur else "NON",
        "Source : planification interne FlySolarLink"))
    story.append(div())
    story.append(row("Zone contrôlée au sol",
        "OUI — périmètre de sécurité à établir avant décollage",
        "Source : EU 2019/947", bg=BG2))
    story.append(div())
    story.append(row("Communication radio", "NON — vol Open A2, non requis"))
    story.append(div())
    story.append(row("Observateurs", "NON", None, bg=BG2))
    story.append(div())
    story.append(row("ERP imprimé", "OUI — Urgences : 112",
        "Source : planification interne FlySolarLink"))
    sp(2)

    # ── 9. CHECKLIST
    story.append(hdr("Checklist — À vérifier le matin du vol"))
    sp(0.5)
    checklist = [
        ("NOTAMs vérifiés sur skeyes.be",           "Aucun NOTAM actif sur zone"),
        ("Géozones confirmées sur map.droneguide.be","Clicker chaque zone colorée"),
        ("Radar IRM consulté",                       "Pas de précipitations prévues"),
        ("IRM bulletin local actualisé",             "Vent rafales acceptables"),
        ("METAR/TAF EBLG actualisé (allmetsat.com)", "Pas de CB ou TSRA"),
        ("KP vérifié (spaceweatherlive.com)",        "KP ≤ 3 recommandé"),
    ]
    if daa_req:
        checklist.insert(0, ("Notification DAA soumise (daa.skeyes.be)", "≥3h avant le vol — OBLIGATOIRE VLL2"))
    if delai >= 5:
        checklist.insert(0, (f"Autorisation écrite reçue (délai {delai}j ouvrables)", "OBLIGATOIRE avant décollage"))
    if remote_req:
        checklist.append(("Remote ID activé et opérationnel", "Obligatoire dans cette zone"))
    for item, note in checklist:
        story.append(chk(False, f"{item}  →  {note}"))
    sp(3)

    # ── PIED DE PAGE
    story.append(HRFlowable(width=BODY, thickness=0.6, color=NAVY))
    sp(1)
    story.append(Paragraph(
        f"FlySolarLink BAV Generator — flysolarlink.com — {generated}  |  "
        "Données : skeyes Public API + IRM meteo.be + allmetsat.com + NOAA SWPC",
        FOOT))

    # Build PDF
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=M, rightMargin=M, topMargin=12*mm, bottomMargin=12*mm,
        title=f"BAV FlySolarLink — {lieu} — {date_vol}")
    doc.build(story)
    return buf



if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
