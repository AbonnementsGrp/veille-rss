# Veille RSS

Application de veille qui centralise des sources d'actualité, qu'elles disposent
ou non d'un flux RSS. Elle produit un flux par source, un flux consolidé, et un
tableau de bord d'état publiés sur GitHub Pages.

- **Tableau de bord** : https://abonnementsgrp.github.io/veille-rss/
- **Flux global** : https://abonnementsgrp.github.io/veille-rss/veille.xml
- **Dépôt** : https://github.com/AbonnementsGrp/veille-rss

## Se servir de l'application

### Suivre la veille dans un lecteur de flux

Trois façons de s'abonner, de la plus simple à la plus fine :

| Ce que vous voulez | L'adresse à ajouter dans votre lecteur |
|---|---|
| Toute la veille en un seul flux | `https://abonnementsgrp.github.io/veille-rss/veille.xml` |
| Toutes les sources d'un coup, séparées | importez `https://abonnementsgrp.github.io/veille-rss/feeds.opml` |
| Une source précise | `https://abonnementsgrp.github.io/veille-rss/<fichier>.xml` (voir la colonne « Flux » du tableau de bord) |

L'OPML s'importe depuis Thunderbird, Feedly, Inoreader, Outlook ou tout autre
lecteur compatible : il crée un dossier contenant toutes les sources d'un coup.

### Vérifier que tout fonctionne

Le [tableau de bord](https://abonnementsgrp.github.io/veille-rss/) affiche, pour
chaque source : son état, le nombre d'articles, la méthode qui a permis de les
récupérer, et le message d'erreur le cas échéant. La même information est
disponible en JSON dans
[`status.json`](https://abonnementsgrp.github.io/veille-rss/status.json), pour
une supervision automatisée.

Les méthodes possibles, de la plus fiable à la plus fragile :

| Méthode | Signification |
|---|---|
| `flux officiel` | Le flux déclaré dans `config/sites.yml` a répondu. |
| `flux détecté` | Aucun flux configuré, mais un flux natif a été trouvé sur le site. |
| `repli : …` | Le flux configuré s'est avéré inexploitable ; les articles viennent de la page. |
| `json_ld+html` | Pas de flux : les articles ont été lus dans les données structurées de la page. |
| `html_selectors` | Articles extraits via des sélecteurs CSS. |
| `generic_links` | Dernier recours : les liens de la page ont été notés et filtrés. |
| `historique conservé` | La source est tombée ; son dernier contenu connu reste publié. |
| `échec` | La source est tombée et aucun historique n'était disponible. |

La veille tourne **toutes les trois heures** via GitHub Actions. Pour forcer une
mise à jour immédiate : onglet *Actions* du dépôt → *Générer et publier les flux
RSS* → *Run workflow*.

## Exécuter en local

Prérequis : Python 3.12 et un accès réseau sortant.

```bash
git clone https://github.com/AbonnementsGrp/veille-rss.git
cd veille-rss
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt   # Windows
# source .venv/bin/activate && pip install -r requirements-dev.txt  # Linux/macOS
```

Lancer une génération complète :

```bash
.venv/Scripts/python.exe generate.py
```

Le script interroge les sources déclarées, écrit les flux dans `public/`, met à jour
`data/history.json`, et affiche un bilan :

```
INFO | CNSA - Actualités : 48 article(s) via flux officiel
ERROR | ANAP - Actualités : Aucun article détecté sur la page
INFO | Bilan : 8 source(s), 6 OK, 2 erreur(s), 164 article(s)
```

Ouvrez ensuite `public/index.html` dans un navigateur pour voir le résultat tel
qu'il sera publié. Une source en erreur n'interrompt jamais les autres.

Pour annuler une génération locale sans conséquence :

```bash
git restore data/history.json public/
```

### Lancer les tests

```bash
.venv/Scripts/python.exe -m pytest
```

Les tests n'accèdent pas au réseau : ils s'appuient sur les jeux de données de
`tests/fixtures/`. La CI les exécute avant toute génération, afin qu'une
régression ne soit jamais publiée.

## Ajouter ou corriger une source

Tout se passe dans [`config/sites.yml`](config/sites.yml). Le minimum est un nom,
une URL de page et un fichier de sortie :

```yaml
  - name: "Localtis - Publics fragiles"
    url: "https://www.banquedesterritoires.fr/publics-fragiles"
    official_feed: "https://www.banquedesterritoires.fr/flux/publics-fragiles/localtis.xml"
    output: "localtis-publics-fragiles.xml"
```

| Clé | Rôle |
|---|---|
| `name` | Libellé affiché ; sert aussi de clé dans l'historique. Le renommer repart d'un historique vide. |
| `url` | Page d'actualités, utilisée pour la découverte de flux et le scraping. |
| `official_feed` | Flux RSS/Atom connu. À ne renseigner qu'après l'avoir testé. |
| `output` | Nom du fichier XML produit. Déduit du `name` si absent. |
| `selectors` | Sélecteurs CSS (`item`, `title`, `description`, `date`) pour les sites sans flux. |
| `link_patterns` | Fragments d'URL caractéristiques des articles, pour orienter le dernier recours. |

Marche à suivre recommandée :

1. Tester le flux supposé (`curl -sI <url>` puis vérifier la présence de `<item>`).
   Un `/feed/` WordPress qui renvoie du HTML n'est pas un flux.
2. S'il est valide, le renseigner dans `official_feed`.
3. Sinon, laisser le moteur chercher : il teste la balise `<link rel="alternate">`
   puis les emplacements conventionnels (`/feed/`, `/rss.xml`, `/atom.xml`…).
4. En dernier ressort, ajouter des `selectors` en s'inspirant du code source de
   la page.
5. Lancer `generate.py` en local et vérifier la ligne de la source dans le
   tableau de bord avant de committer.

Les réglages globaux (nombre d'articles par flux, taille de l'historique,
délai réseau, user-agent) sont dans la section `settings` du même fichier.

## Architecture

```text
veille-rss/
├── generate.py              point d'entrée : python generate.py
├── veille/
│   ├── config.py            chemins du projet, lecture de sites.yml
│   ├── models.py            l'article (Item) et la déduplication
│   ├── text.py              nettoyage des textes
│   ├── dates.py             normalisation ISO 8601 UTC et tri
│   ├── fetch.py             session HTTP, détection d'un contenu de flux
│   ├── feeds.py             lecture RSS/Atom, découverte du flux d'un site
│   ├── extract.py           extraction HTML : JSON-LD, sélecteurs, liens
│   ├── history.py           historique des articles vus
│   ├── output.py            écriture des flux, de l'OPML, du tableau de bord
│   └── pipeline.py          orchestration d'une exécution
├── tests/                   suite pytest + fixtures hors réseau
├── config/sites.yml         définition des sources
├── data/history.json        historique (committé, sert de mémoire entre les runs)
├── public/                  sorties publiées par GitHub Pages
└── .github/workflows/       génération planifiée toutes les 3 h
```

Le traitement d'une source suit toujours le même enchaînement : flux officiel
configuré, sinon flux natif découvert, sinon extraction HTML ; puis
normalisation (titre, URL, date, résumé), déduplication, fusion avec
l'historique, écriture du flux individuel et intégration au flux global.

### Points de vigilance

- **Les dates sont toujours stockées en ISO 8601 UTC.** Le parseur souple lit les
  dates françaises jour-en-premier, ce qui inverse jour et mois sur une chaîne
  ISO : `veille/dates.py` reconnaît donc l'ISO en premier. Ne pas contourner.
- **`data/history.json` est committé.** C'est la mémoire du projet : il permet de
  compter les nouveautés et de republier une source momentanément tombée.
- **Le nom d'une source est sa clé d'historique.** Le modifier revient à repartir
  de zéro pour cette source.
- **Les liens sont débarrassés de leurs paramètres de suivi** (`utm_*`, `pk_*`,
  `fbclid`…) dès la création de l'article : c'est le lien qui porte son identité,
  deux rubriques d'un même site ne doivent pas produire deux fois l'article.

## Sources suivies

### Enfance & Éducation

- **Enfance & Jeunesse Infos** — https://www.enfancejeunesseinfos.fr/tag/veille-juridique/
  — flux officiel : `.../tag/veille-juridique/feed/`
- **Les Pros de la Petite Enfance** — https://www.lesprosdelapetiteenfance.fr/actualites/
  — flux natif découvert automatiquement
- **Localtis — Jeunesse, éducation et formation** — flux officiel :
  `https://www.banquedesterritoires.fr/flux/jeunesse-education-et-formation/localtis.xml`

### Santé, Social & Sénior

- **CNSA** — https://www.cnsa.fr/actualites — flux officiel : `https://www.cnsa.fr/flux-rss.xml/article`
- **IGAS** — https://igas.gouv.fr/ — flux à générer
- **Localtis — Publics fragiles** — flux officiel :
  `https://www.banquedesterritoires.fr/flux/publics-fragiles/localtis.xml`
  — attention : rubrique dormante côté Localtis, aucun article publié depuis avril 2024
- **ANAP** — https://www.anap.fr/s/actualites — flux à générer ; site dynamique

### Culture

- **Observatoire des Politiques Culturelles** — https://www.observatoire-culture.net/

### Tourisme

- **ADN Tourisme** — https://www.adn-tourisme.fr/publications/actus/

### Restauration

- **C2L Solutions** — https://www.c2lsolutions.fr/category/la-restauration-collective-actualites/
  — le `/feed/` annoncé renvoie du HTML : articles extraits de la page par repli
- **SNRC** — https://www.snrc.fr/le-snrc/actualites-snrc/ — flux à générer

## Reste à faire

1. Ajouter la source IGAS à `config/sites.yml`.
2. Écrire les extracteurs manquants : SNRC, IGAS, page actus d'ADN Tourisme.
3. Traiter l'ANAP, dont la page d'actualités est rendue en JavaScript.
4. Nettoyer les résumés doublement échappés issus de certains flux WordPress.
5. Porter les champs prévus dans `sites.yml` : nom court, ordre, thème.

## Contraintes

- Solution gratuite : GitHub, GitHub Actions, GitHub Pages.
- Aucun contournement d'authentification, de CAPTCHA, d'abonnement ou de
  protection d'accès.
- Les flux officiels sont privilégiés lorsqu'ils existent et fonctionnent.
