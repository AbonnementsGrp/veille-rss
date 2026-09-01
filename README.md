# Veille RSS

Application de veille qui centralise des sources d'actualité, qu'elles disposent
ou non d'un flux RSS. Elle produit un flux par source, un flux consolidé, et un
tableau de bord d'état publiés sur GitHub Pages.

- **Tableau de bord** : https://abonnementsgrp.github.io/veille-rss/
- **Flux global** : https://abonnementsgrp.github.io/veille-rss/veille.xml
- **Dépôt** : https://github.com/AbonnementsGrp/veille-rss

> **Vous voulez seulement suivre la veille ?** Le
> [guide d'utilisation](GUIDE-UTILISATEUR.md) explique comment s'abonner selon
> votre lecteur de flux, comment lire le tableau de bord et ce que couvre chaque
> source. Le présent README s'adresse à qui fait évoluer l'application.

## Se servir de l'application

### Suivre la veille dans un lecteur de flux

Trois adresses, détaillées dans le [guide d'utilisation](GUIDE-UTILISATEUR.md) :
le flux global `veille.xml`, le fichier d'abonnements `feeds.opml` — qui crée un
dossier par domaine à l'import — et le flux propre à chaque source.

### Vérifier que tout fonctionne

Le [tableau de bord](https://abonnementsgrp.github.io/veille-rss/) affiche, pour
chaque source : son état, le nombre d'articles, la méthode qui a permis de les
récupérer, et le message d'erreur le cas échéant. Les sources y sont groupées
par domaine, dans l'ordre défini par `settings.themes`. La même information est
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
| `generic_links` | Les liens de la page ont été notés et filtrés. |
| `plan de site` | Site rendu en JavaScript : URL et dates viennent de son sitemap.xml. |
| `historique conservé` | La source est tombée ; son dernier contenu connu reste publié. |
| `échec` | La source est tombée et aucun historique n'était disponible. |

La veille tourne **toutes les trois heures** via GitHub Actions. Pour forcer une
mise à jour immédiate : onglet *Actions* du dépôt → *Générer et publier les flux
RSS* → *Run workflow*.

Le tableau de bord indique l'ancienneté de la dernière génération et affiche un
avertissement au-delà de neuf heures, soit trois créneaux manqués. Le calcul se
fait dans le navigateur : une page statique qui cesse d'être regénérée se
figerait sinon avec sa date, sans que rien ne le signale.

Le seuil n'est pas théorique : sur trente exécutions planifiées entre le 25 et le
31 août 2026, l'écart médian était de 3,5 heures, mais quatre créneaux ont sauté
pendant 10 à 15 heures sans qu'aucune exécution n'échoue. GitHub décale, voire
annule, les tâches planifiées quand la file d'attente s'allonge.

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

## Purger l'historique d'une source

L'historique complète chaque flux : après un changement de méthode
d'extraction, les articles récoltés par l'ancienne continuent d'être publiés.

```bash
.venv/Scripts/python.exe scripts/purger_source.py --lister          # sources connues
.venv/Scripts/python.exe scripts/purger_source.py "ADN Tourisme"    # aperçu
.venv/Scripts/python.exe scripts/purger_source.py "ADN Tourisme" --appliquer
.venv/Scripts/python.exe generate.py                                # reconstitue le flux
```

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
| `name` | Nom complet ; sert aussi de clé dans l'historique. Le renommer repart d'un historique vide. |
| `short_name` | Nom affiché sur le tableau de bord et dans l'OPML. À défaut, `name` est utilisé. |
| `theme` | Domaine de regroupement. Doit figurer dans `settings.themes`, sinon la source passe en fin de tableau sous « Autres ». |
| `order` | Rang dans le domaine. À défaut, l'ordre du fichier fait foi. |
| `url` | Page d'actualités, utilisée pour la découverte de flux et le scraping. |
| `official_feed` | Flux RSS/Atom connu. À ne renseigner qu'après l'avoir testé. |
| `output` | Nom du fichier XML produit. Déduit du `name` si absent. |
| `mode` | `page` interdit la découverte de flux : la page devient la seule source, utile quand le flux racine du site n'a rien à voir avec la rubrique suivie. `sitemap` lit le plan de site, seul recours pour un site rendu en JavaScript. |
| `sitemap` | URL du plan de site à lire, obligatoire avec `mode: sitemap`. |
| `selectors` | Sélecteurs CSS (`item`, `title`, `description`, `date`) pour les sites sans flux. |
| `link_patterns` | Fragments d'URL caractéristiques des articles, pour orienter le dernier recours. |

Marche à suivre recommandée :

1. Tester le flux supposé (`curl -sI <url>` puis vérifier la présence de `<item>`).
   Un `/feed/` WordPress qui renvoie du HTML n'est pas un flux.
2. S'il est valide, le renseigner dans `official_feed`.
3. Sinon, laisser le moteur chercher, dans cet ordre : le flux propre à la
   rubrique (`<url de la page>/feed/`), puis celui que la page déclare en
   `<link rel="alternate">`, puis les emplacements conventionnels à la racine.
   La rubrique passe avant la déclaration de la page : WordPress y annonce le
   flux global du site, thématiquement plus large que la rubrique suivie.
4. En dernier ressort, ajouter des `selectors` en s'inspirant du code source de
   la page.
5. Lancer `generate.py` en local et vérifier la ligne de la source dans le
   tableau de bord avant de committer.

Les réglages globaux sont dans la section `settings` du même fichier : nombre
d'articles par flux, taille de l'historique, délai réseau, user-agent, liste
ordonnée des domaines (`themes`), et enrichissement des résumés manquants
(`enrich_descriptions`, `max_enrichments_per_run`).

## Architecture

```text
veille-rss/
├── generate.py              point d'entrée : python generate.py
├── veille/
│   ├── config.py            chemins du projet, lecture de sites.yml
│   ├── models.py            l'article (Item) et la déduplication
│   ├── text.py              nettoyage des textes et des résumés
│   ├── urls.py              normalisation des liens d'articles
│   ├── dates.py             normalisation ISO 8601 UTC et tri
│   ├── fetch.py             session HTTP, détection d'un contenu de flux
│   ├── feeds.py             lecture RSS/Atom, découverte du flux d'un site
│   ├── extract.py           extraction HTML : JSON-LD, sélecteurs, liens
│   ├── sitemap.py           extraction depuis un plan de site
│   ├── enrich.py            résumé lu sur la page d'un article
│   ├── history.py           historique des articles vus
│   ├── output.py            écriture des flux, de l'OPML, du tableau de bord
│   └── pipeline.py          orchestration d'une exécution
├── tests/                   suite pytest + fixtures hors réseau
├── scripts/                 outils de maintenance
├── GUIDE-UTILISATEUR.md     documentation à destination des lecteurs
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
- **Un flux inchangé doit produire un fichier identique.** `lastBuildDate`
  porte donc la date du plus récent article, pas l'heure de génération, et la
  CI ne committe que lorsqu'un article change. Le site publié reste à jour à
  chaque exécution : l'artefact Pages vient du dossier `public`, pas du commit.
- **Les liens sont débarrassés de leurs paramètres de suivi** (`utm_*`, `pk_*`,
  `fbclid`…) dès la création de l'article : c'est le lien qui porte son identité,
  deux rubriques d'un même site ne doivent pas produire deux fois l'article.

## Sources suivies

### Enfance & Éducation

- **Enfance & Jeunesse Infos** — https://www.enfancejeunesseinfos.fr/tag/veille-juridique/
  — flux officiel : `.../tag/veille-juridique/feed/`
- **Les Pros de la Petite Enfance** — https://www.lesprosdelapetiteenfance.fr/actualites/
  — flux natif de la rubrique, découvert automatiquement
- **Localtis — Jeunesse, éducation et formation** — flux officiel :
  `https://www.banquedesterritoires.fr/flux/jeunesse-education-et-formation/localtis.xml`

### Santé, Social & Sénior

- **CNSA** — https://www.cnsa.fr/actualites — flux officiel :
  `https://www.cnsa.fr/flux-rss.xml/article`. Ce flux sert chaque article deux
  fois, sous `/actualites/x` et `/index%2Ephp/actualites/x` ; la déduplication
  s'en charge.
- **IGAS** — https://igas.gouv.fr/actualites — flux officiel :
  `https://igas.gouv.fr/rss.xml`, qui couvre actualités et rapports
- **Localtis — Publics fragiles** — flux officiel :
  `https://www.banquedesterritoires.fr/flux/publics-fragiles/localtis.xml`
  — attention : rubrique dormante côté Localtis, aucun article publié depuis avril 2024
- **ANAP** — https://www.anap.fr/s/actualites — `mode: sitemap`. Le site est
  rendu en JavaScript : ses pages ne livrent aucun titre à un client HTTP. Les
  titres sont donc déduits des URL du plan de site, d'où des libellés parfois
  sans accents ni majuscules.

### Culture

- **Observatoire des Politiques Culturelles** — https://www.observatoire-culture.net/

### Tourisme

- **ADN Tourisme** — https://www.adn-tourisme.fr/publications/actus/
  — flux de la rubrique actus ; le flux racine du site, lui, mêle actualités et
  offres d'emploi

### Restauration

- **C2L Solutions** — https://www.c2lsolutions.fr/category/la-restauration-collective-actualites/
  — le `/feed/` annoncé renvoie du HTML : articles extraits de la page par repli
- **SNRC** — https://www.snrc.fr/le-snrc/actualites-snrc/ — `mode: page` et
  sélecteurs : le flux racine du site ne contient que deux billets sans rapport

## Points connus, sans action prévue

- **Les titres ANAP dépendent du slug de l'URL.** Vérifié : une page d'article
  ne contient que `<title>Site de l'Anap</title>`, aucune balise Open Graph, et
  pas même le texte de l'article — tout est rendu en JavaScript. Le plan de site
  reste la seule source, et le slug le seul titre disponible. Beaucoup sont
  corrects (« Journée nationale de la transformation du handicap »), d'autres
  sont laconiques (« Webinaire rdv transfo ») : ils le sont à la source.
  Y remédier supposerait un navigateur sans tête à chaque exécution.
- **anap.fr sert une chaîne de certificats incomplète** depuis le 28 août 2026,
  d'où un `CERTIFICATE_VERIFY_FAILED`. Le défaut est côté site : il touche aussi
  bien la CI que les postes de travail, alors que la même URL répondait
  normalement le 27. La source bascule sur son historique et reste publiée, avec
  son erreur visible au tableau de bord. Y remédier de notre côté supposerait de
  fournir nous-mêmes le certificat intermédiaire manquant ; à faire seulement si
  l'ANAP tarde à corriger.
- **La rubrique Publics fragiles de Localtis est dormante** : aucun article
  publié depuis avril 2024. Le flux est valide, la source ne l'alimente plus.

## Contraintes

- Solution gratuite : GitHub, GitHub Actions, GitHub Pages.
- Aucun contournement d'authentification, de CAPTCHA, d'abonnement ou de
  protection d'accès.
- Les flux officiels sont privilégiés lorsqu'ils existent et fonctionnent.
