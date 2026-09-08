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
par domaine ; domaines et sources sont classés par ordre alphabétique, « Autres »
regroupant en dernier les sources sans domaine. La même information est
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
| `plan de site` | Site rendu en JavaScript : URL et dates viennent de son sitemap.xml ; titres et résumés sont ensuite lus page par page par le navigateur sans tête. |
| `navigateur : …` | La page a été rendue par le navigateur sans tête avant l'extraction (`render: true`). |
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

Prérequis : Python 3.12 et un accès réseau sortant. Les sources rendues en
JavaScript (`render: true`, comme l'ANAP) demandent en plus un Chromium sans
tête, installé une fois pour toutes après les dépendances :

```
python -m playwright install chromium
```

Sans lui, tout le reste fonctionne ; ces sources seules passent en erreur, avec
la marche à suivre dans le message.

### PowerShell (Windows)

```powershell
git clone https://github.com/AbonnementsGrp/veille-rss.git
cd veille-rss
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

L'activation fonctionne sous la politique d'exécution `RemoteSigned` par défaut
de Windows : `Activate.ps1` est créé localement, il n'est donc pas bloqué. Une
fois le venv activé, `python` et `pytest` désignent ceux du projet :

```powershell
python generate.py                  # génération complète
python -m pytest                    # tests
Invoke-Item .\public\index.html     # ouvrir le tableau de bord produit
```

Sans activer le venv, préfixez chaque commande par son interpréteur :

```powershell
.\.venv\Scripts\python.exe generate.py
```

PowerShell affiche correctement les accents des journaux, ce que Git Bash ne fait
pas sur ce poste : préférez-le pour lire les bilans d'exécution.

### Bash (Linux, macOS, Git Bash)

```bash
git clone https://github.com/AbonnementsGrp/veille-rss.git
cd veille-rss
python -m venv .venv
source .venv/bin/activate          # .venv/Scripts/activate sous Git Bash
pip install -r requirements-dev.txt
python generate.py
python -m pytest
```

### Ce que fait une génération

Le script interroge les sources déclarées, écrit les flux dans `public/`, met à
jour `data/history.json`, et affiche un bilan :

```
INFO | CNSA - Actualités : 28 article(s) via flux officiel
WARNING | C2L Solutions : …/feed/ ne sert pas un flux (contenu text/html). Repli sur la page d'actualités.
INFO | C2L Solutions : 10 article(s) via repli : html_selectors
INFO | Bilan : 11 source(s), 11 OK, 0 erreur(s), 287 article(s)
```

Ouvrez `public/index.html` dans un navigateur pour voir le résultat tel qu'il sera
publié. Une source en erreur n'interrompt jamais les autres.

Pour annuler une génération locale sans conséquence :

```
git restore data/history.json public/
```

### Les tests

Ils n'accèdent pas au réseau : ils s'appuient sur les jeux de données de
`tests/fixtures/`. La CI les exécute avant toute génération, afin qu'une
régression ne soit jamais publiée.

## Purger l'historique d'une source

L'historique complète chaque flux : après un changement de méthode
d'extraction, les articles récoltés par l'ancienne continuent d'être publiés.

```powershell
python scripts/purger_source.py --lister          # sources connues
python scripts/purger_source.py "ADN Tourisme"    # aperçu, n'écrit rien
python scripts/purger_source.py "ADN Tourisme" --appliquer
python generate.py                                # reconstitue le flux
```

(venv activé ; sinon préfixez par `.\.venv\Scripts\python.exe`)

## Ajouter une source

Trois voies, de la plus simple à la plus manuelle. Les deux premières reposent sur
la même enquête automatique (`veille/onboarding.py`) : à partir de l'adresse
d'une page d'actualités, elle cherche le flux, extrait les articles, propose un
nom, et rend un verdict — prête, à vérifier, ou réglage manuel — avec ses
réserves.

### Par formulaire, sans outillage (recommandé pour les demandeurs)

N'importe qui avec un compte GitHub ouvre le formulaire *Proposer une nouvelle
source* (bouton sur le tableau de bord, ou onglet *Issues* → *New issue*). Le
workflow [nouvelle-source.yml](.github/workflows/nouvelle-source.yml) enquête et
publie le résultat en commentaire, avec l'aperçu des articles et le bloc de
configuration qu'il écrirait. Il pose une étiquette selon le verdict :
`enquete-ok`, `enquete-a-verifier`, `enquete-manuel` ou `enquete-erreur`. Les
étiquettes, dont `approuvé`, sont créées par le workflow lui-même au premier
passage : rien à préparer dans le dépôt. Le formulaire est reconnu à son premier
champ, pas à son étiquette.

**Rôle du responsable** : lire le commentaire, puis poser l'étiquette
**approuvé** si la source convient. Le workflow ajoute alors le bloc à
`config/sites.yml`, committe, ferme l'issue, et la génération repart d'elle-même
puisque tout push sur `config/` la déclenche. Un verdict « manuel » ou une
adresse déjà suivie sont refusés même approuvés, et l'étiquette est retirée.

Deux garde-fous. Seules les personnes ayant au moins le droit *triage* sur le
dépôt peuvent poser une étiquette : un demandeur ne peut pas approuver sa propre
demande. Et le corps de l'issue, écrit par le demandeur, ne transite jamais par
un shell : il passe par une variable d'environnement lue par Python.

**Relancer une enquête** : modifier l'issue (titre ou corps) suffit, l'événement
*edited* déclenche le workflow. C'est aussi le moyen de traiter une issue ouverte
avant que le workflow n'existe.

Une subtilité qui a coûté une première exécution : dans une expression `if:`,
les chaînes vont entre **guillemets simples**. Avec des doubles, GitHub refuse
tout le fichier sans message, le workflow apparaît sous son chemin au lieu de
son nom dans la liste des workflows, et rien ne se déclenche. Les marqueurs de
reconnaissance des formulaires sont choisis sans apostrophe pour cette raison.

### Ajouter un domaine

Les domaines vivent à deux endroits : `settings.themes` dans `config/sites.yml`,
qui dit quels domaines sont reconnus, et la liste déroulante du formulaire de
source. `veille/themes.py` est le seul à les modifier, et les modifie ensemble,
en les réécrivant par ordre alphabétique ; un test vérifie qu'ils restent
identiques et triés. L'affichage du tableau de bord suit le même ordre : il n'y
a pas de position à choisir.

Par formulaire : *Proposer un nouveau domaine*, traité par
[nouveau-domaine.yml](.github/workflows/nouveau-domaine.yml) sur le même schéma
que les sources — vérification en commentaire, étiquette **approuvé**, écriture
et commit automatiques. En ligne de commande :

```powershell
python scripts/ajouter_theme.py "Logement & Habitat"            # aperçu
python scripts/ajouter_theme.py "Logement & Habitat" --ecrire
git add config/sites.yml .github/ISSUE_TEMPLATE/nouvelle-source.yml
```

Un domaine sans source n'apparaît pas sur le tableau de bord ; il apparaît dès
qu'une source lui est rattachée.

### Renommer un domaine

Le nouveau nom remplace l'ancien aux trois endroits où il figure : la liste des
domaines, la clé `theme` des sources concernées, la liste déroulante du
formulaire de source. L'ancien nom est reconnu sans égard à la casse ni aux
accents. Par formulaire, *Renommer un domaine*, traité par
[renommer-domaine.yml](.github/workflows/renommer-domaine.yml) ; en ligne de
commande :

```powershell
python scripts/renommer_theme.py "Culture" "Arts & Culture"            # aperçu
python scripts/renommer_theme.py "Culture" "Arts & Culture" --ecrire
```

### Supprimer une source

Une source vit à trois endroits : son bloc dans `config/sites.yml`, ses articles
dans `data/history.json`, son flux dans `public/`. La suppression retire les
trois — sinon le flux resterait en ligne, figé. La source est reconnue par son
nom complet ou son nom court. Par formulaire, *Supprimer une source*, traité par
[supprimer-source.yml](.github/workflows/supprimer-source.yml), avec un
récapitulatif à lire avant d'approuver puisque l'opération est irréversible ; en
ligne de commande :

```powershell
python scripts/supprimer_source.py "IGAS"            # aperçu de ce qui serait retiré
python scripts/supprimer_source.py "IGAS" --ecrire
git add -A config/sites.yml data/history.json public/
```

### En ligne de commande

```powershell
python scripts/ajouter_source.py https://www.exemple.fr/actualites/
```

Sans option, le script enquête, affiche l'aperçu et le bloc proposé, et n'écrit
rien. Dans un terminal, il demande le nom et le domaine s'ils manquent.

```powershell
python scripts/ajouter_source.py https://www.exemple.fr/actualites/ --theme "Culture" --ecrire
python generate.py              # vérifier la ligne de la source sur le tableau de bord
git add config/sites.yml
git commit -m "Ajouter la source Exemple"
git push                        # la CI régénère et publie
```

`--nom` et `--court` fixent les libellés, `--forcer` passe outre un verdict
« manuel » ou une adresse déjà suivie, `--json` sert au traitement automatique.

### À la main, dans `config/sites.yml`

Nécessaire quand l'enquête rend un verdict « manuel » : site en JavaScript,
page sans structure lisible. Le minimum est un nom, une URL et un fichier de
sortie :

```yaml
  - name: "Localtis - Publics fragiles"
    short_name: "Localtis — Publics fragiles"
    theme: "Santé, social & séniors"
    url: "https://www.banquedesterritoires.fr/thematiques/publics-fragiles"
    official_feed: "https://www.banquedesterritoires.fr/flux/publics-fragiles/localtis.xml"
    output: "localtis-publics-fragiles.xml"
```

| Clé | Rôle |
|---|---|
| `name` | Nom complet ; sert aussi de clé dans l'historique. Le renommer repart d'un historique vide. |
| `short_name` | Nom affiché sur le tableau de bord et dans l'OPML. À défaut, `name` est utilisé. |
| `theme` | Domaine de regroupement. À déclarer dans `settings.themes` pour qu'il soit proposé dans le formulaire ; sans domaine, la source va sous « Autres », en dernier. |
| `url` | Page d'actualités, utilisée pour la découverte de flux et le scraping. |
| `official_feed` | Flux RSS/Atom connu. À ne renseigner qu'après l'avoir testé. |
| `feed_categories` | Ne garder du flux que les articles étiquetés d'une de ces catégories. Pour un site WordPress dont les flux de rubrique sont désactivés mais dont le flux général (`/feed/?post_type=post`) étiquette ses articles. |
| `output` | Nom du fichier XML produit. Déduit du `name` si absent. |
| `mode` | `page` interdit la découverte de flux : la page devient la seule source, utile quand le flux racine du site n'a rien à voir avec la rubrique suivie. `sitemap` lit le plan de site, qui donne adresses et dates d'un site rendu en JavaScript. |
| `sitemap` | URL du plan de site à lire, obligatoire avec `mode: sitemap`. |
| `render` | `true` : les pages du site sont rendues par le navigateur sans tête (Chromium via Playwright) avant lecture. Avec `mode: page`, la page d'actualités elle-même ; avec `mode: sitemap`, les pages d'articles, pour en tirer titre et résumé. Le formulaire d'ajout le propose de lui-même quand seule la page rendue montre des articles. |
| `render_wait_for` | Sélecteur CSS dont l'apparition signale que la page rendue est complète (`'meta[property="og:title"]'` pour l'ANAP). Sans lui, la veille attend le calme du réseau puis la stabilité du document. |
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
d'articles par flux, taille de l'historique, délai réseau, user-agent, liste des
domaines reconnus (`themes` — son ordre est sans effet, l'affichage est
alphabétique), et enrichissement des résumés manquants (`enrich_descriptions`,
`max_enrichments_per_run`).

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
│   ├── fetch.py             session HTTP, lot de certificats, détection d'un flux
│   ├── browser.py           navigateur sans tête (Playwright) pour les sites en JavaScript
│   ├── feeds.py             lecture RSS/Atom, découverte du flux d'un site
│   ├── extract.py           extraction HTML : JSON-LD, sélecteurs, liens
│   ├── sitemap.py           extraction depuis un plan de site
│   ├── enrich.py            résumé lu sur la page d'un article
│   ├── onboarding.py        enquête sur une URL en vue d'en faire une source
│   ├── themes.py            domaines : ajout, renommage, configuration et formulaire ensemble
│   ├── sources.py           suppression d'une source : configuration, historique, flux
│   ├── issues.py            lecture commune des formulaires d'issue
│   ├── history.py           historique des articles vus
│   ├── output.py            écriture des flux, de l'OPML, du tableau de bord
│   └── pipeline.py          orchestration d'une exécution
├── tests/                   suite pytest + fixtures hors réseau
├── scripts/                 ajouter_source.py, supprimer_source.py, ajouter_theme.py,
│                            renommer_theme.py, purger_source.py, issue_*.py
├── .github/ISSUE_TEMPLATE/  formulaires : source (ajout, suppression), domaine (ajout, renommage)
├── GUIDE-UTILISATEUR.md     documentation à destination des lecteurs
├── config/sites.yml         définition des sources
├── config/certs/            certificats intermédiaires que des sites oublient d'envoyer
├── data/history.json        historique (committé, sert de mémoire entre les runs)
├── public/                  sorties publiées par GitHub Pages
└── .github/workflows/       génération planifiée toutes les 3 h
```

Le traitement d'une source suit toujours le même enchaînement : flux officiel
configuré, sinon flux natif découvert, sinon extraction HTML ; puis
normalisation (titre, URL, date, résumé), déduplication, fusion avec
l'historique, écriture du flux individuel et intégration au flux global.

Pour un site rendu en JavaScript, la page est d'abord rendue par un Chromium sans
tête (`veille/browser.py`, Playwright) et l'extraction reçoit le document tel
que l'utilisateur le voit, shadow DOM compris. La CI installe ce navigateur à
chaque exécution (une trentaine de secondes, mis en cache) ; il n'est lancé que
si une source le demande.

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
- **Un site à la chaîne de certificats incomplète se corrige dans `config/certs/`,
  jamais en désactivant la vérification.** La session HTTP vérifie les sites avec
  le lot de certifi complété des fichiers PEM de ce dossier (et du lot que
  `REQUESTS_CA_BUNDLE` ou `CURL_CA_BUNDLE` désignerait sur le poste). Pour
  ajouter un intermédiaire : lire son adresse dans le certificat du site
  (`openssl x509 -in feuille.pem -noout -ext authorityInfoAccess`), le
  télécharger, le convertir en PEM (`openssl x509 -inform DER -in x.crt -out
  config/certs/x.pem`) et vérifier qu'il remonte bien à une racine connue
  (`openssl verify -CAfile "$(python -c 'import certifi;print(certifi.where())')"
  config/certs/x.pem`). Un certificat qui ne remonte à rien ne doit pas entrer.

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
- **ANAP** — https://www.anap.fr/s/actualites — `mode: sitemap` et
  `render: true`. Le site est rendu en JavaScript : ses pages ne livrent aucun
  titre à un client HTTP. Le plan de site donne les adresses et les dates ; le
  navigateur sans tête lit ensuite chaque page d'article, une fois pour toutes,
  pour en tirer le vrai titre et le résumé. En attendant cette lecture, le
  titre est déduit de l'URL.

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

- **Les titres ANAP naissent du slug de l'URL, puis sont corrigés.** Une page
  d'article ne livre à un client HTTP que `<title>Site de l'Anap</title>` : tout
  est rendu en JavaScript, dans le shadow DOM de composants Salesforce. Depuis
  le 8 septembre 2026, le navigateur sans tête lit chaque page une fois (budget
  partagé de 25 pages par exécution) et en tire le titre — complété depuis
  l'en-tête de l'article, car le site coupe ses métadonnées de partage à
  soixante caractères — et le résumé. Le titre corrigé ne change ni l'identité
  de l'article ni son guid : un lecteur ne le revoit pas comme une nouveauté.
  Les dates restent celles du plan de site.
- **anap.fr sert une chaîne de certificats incomplète** depuis le 28 août 2026 :
  le site n'envoie que son propre certificat, sans l'intermédiaire « DigiCert
  Global G2 TLS RSA SHA256 2020 CA1 » qui le relie à une racine connue, d'où un
  `CERTIFICATE_VERIFY_FAILED`. Le défaut est côté site. Depuis le 8 septembre
  2026 la veille fournit elle-même cet intermédiaire
  (`config/certs/digicert-global-g2-tls-rsa-sha256-2020-ca1.pem`, valable
  jusqu'en mars 2031, téléchargé à l'adresse que le certificat du site indique
  lui-même) et la collecte a repris. Le fichier pourra être supprimé quand
  l'ANAP aura corrigé sa configuration ; le laisser ne gêne pas.
- **La rubrique Publics fragiles de Localtis est dormante** : aucun article
  publié depuis avril 2024. Le flux est valide, la source ne l'alimente plus.

## Contraintes

- Solution gratuite : GitHub, GitHub Actions, GitHub Pages.
- Aucun contournement d'authentification, de CAPTCHA, d'abonnement ou de
  protection d'accès.
- Les flux officiels sont privilégiés lorsqu'ils existent et fonctionnent.
