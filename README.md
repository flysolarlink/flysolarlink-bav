# FlySolarLink BAV Generator

Application web de génération automatique de Briefings Avant Vol (BAV)
pour pilotes drone professionnels — conforme École du Drone Belgique / EU 2019/947.

## Données récupérées automatiquement

| Source | Données | API |
|--------|---------|-----|
| skeyes Public API | Géozones UAS, restrictions, délais | api-cis.skeyes.be/public/uas-zones |
| IRM meteo.be | Bulletin météo local | Scraping HTML |
| allmetsat.com | METAR / TAF EBLG | Scraping HTML |
| NOAA SWPC | Indice KP géomagnétique | services.swpc.noaa.gov |

## Installation locale

```bash
cd bav_app
pip install -r requirements.txt
python app.py
# Ouvrir http://localhost:5000
```

## Déploiement Railway.app (gratuit)

1. Créer un compte sur railway.app
2. New Project → Deploy from GitHub
3. Uploader ce dossier
4. Ajouter fichier `Procfile` : `web: python app.py`
5. Variables d'environnement : `PORT=5000`

## Structure

```
bav_app/
├── app.py              # Backend Flask + génération PDF
├── templates/
│   └── index.html      # Interface utilisateur
├── requirements.txt    # Dépendances Python
└── README.md
```

## Fonctionnalités

- ✅ Formulaire mission (drone, lieu, date/heure)
- ✅ Géozones automatiques via skeyes Public API (sans token)
- ✅ Détection pièges : délai 5j ouvrables, altitude VLL2, Remote ID
- ✅ Météo IRM + METAR/TAF EBLG en temps réel
- ✅ KP NOAA SWPC en temps réel
- ✅ Génération PDF BAV format École du Drone
- ✅ Rappels AIP ENR 5.1 / ENR 5.2 intégrés

## Flotte FlySolarLink supportée

- DJI Mavic 3 (C1)
- DJI Mini 4 Pro / Mini 5 Pro (C0)
- DJI Matrice 4T / 4E (C2)
- DJI Matrice 400 RTK (C3)

---
FlySolarLink — flysolarlink.com — contact@flysolarlink.com
