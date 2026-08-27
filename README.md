# Veille RSS

Application de veille permettant de centraliser des sources disposant ou
non d'un flux RSS natif.

## Objectif

Le projet doit : - utiliser les flux RSS officiels lorsqu'ils existent
et fonctionnent ; - générer un RSS depuis une page d'actualités
lorsqu'aucun flux exploitable n'est disponible ; - produire un flux
individuel par source et un flux consolidé `veille.xml` ; - conserver un
historique des articles ; - exposer l'état des sources ; - s'exécuter
toutes les trois heures via GitHub Actions ; - publier les résultats
avec GitHub Pages.

## Architecture

``` text
veille-rss/
├── .github/workflows/
├── config/sites.yml
├── data/history.json
├── public/
├── generate.py
├── requirements.txt
├── .gitignore
└── README.md
```

## Sources à prendre en charge

### Enfance & Éducation

-   **Enfance & Jeunesse Infos** ---
    https://www.enfancejeunesseinfos.fr/tag/veille-juridique/ --- RSS
    officiel :
    `https://www.enfancejeunesseinfos.fr/tag/veille-juridique/feed/`
-   **Les Pros de la Petite Enfance** ---
    https://www.lesprosdelapetiteenfance.fr/actualites/ --- flux à
    générer.
-   **Localtis -- Jeunesse, Éducation et Formation** --- RSS officiel :
    `https://www.banquedesterritoires.fr/flux/jeunesse-education-et-formation/localtis.xml`

### Santé, Social & Sénior

-   **CNSA** --- https://www.cnsa.fr/actualites --- RSS officiel :
    `https://www.cnsa.fr/flux-rss.xml/article`
-   **IGAS** --- https://igas.gouv.fr/ --- RSS à fiabiliser ou flux à
    générer. L'URL filtrée précédemment identifiée ne fonctionne pas
    actuellement.
-   **Localtis -- Publics fragiles** --- RSS officiel :
    `https://www.banquedesterritoires.fr/flux/publics-fragiles/localtis.xml`
-   **ANAP** --- https://www.anap.fr/s/actualites --- flux à générer ;
    site dynamique.

### Culture

-   **Observatoire des Politiques Culturelles (OPC)** ---
    https://www.observatoire-culture.net/ --- flux à générer.

### Tourisme

-   **ADN Tourisme** --- https://www.adn-tourisme.fr/publications/actus/
    --- flux à générer.

### Restauration

-   **C2L Solutions** ---
    https://www.c2lsolutions.fr/category/la-restauration-collective-actualites/
    --- flux à générer ; RSS WordPress à vérifier.
-   **SNRC** --- https://www.snrc.fr/le-snrc/actualites-snrc/ --- flux à
    générer.

## Fonctionnement attendu

Pour chaque source : 1. utiliser le RSS officiel fonctionnel s'il est
configuré ; 2. sinon rechercher un RSS/Atom natif ; 3. sinon extraire
les actualités via HTML, JSON-LD ou une stratégie spécifique ; 4.
normaliser titre, URL, date, source et si possible résumé ; 5. générer
le flux individuel ; 6. intégrer les articles au flux global ; 7.
enregistrer l'état de la source et conserver l'historique.

Une source en erreur ne doit pas empêcher le traitement des autres.

## Sorties

-   `public/veille.xml` : flux consolidé ;
-   un fichier XML par source ;
-   `public/status.json` : état de la dernière exécution et erreurs
    éventuelles.

Publication : `https://abonnementsgrp.github.io/veille-rss/`

Flux global attendu :
`https://abonnementsgrp.github.io/veille-rss/veille.xml`

## Automatisation

GitHub Actions exécute le traitement automatiquement toutes les trois
heures et doit également permettre un lancement manuel.

## Configuration

Les sources sont centralisées dans `config/sites.yml`. La configuration
doit pouvoir porter : nom, nom court, ordre, thème, URL de page, URL RSS
éventuelle, mode de traitement, fichier de sortie et
stratégie/sélecteurs spécifiques.

## Priorités de développement

1.  Fiabiliser les 11 sources.
2.  Valider les RSS officiels avant utilisation.
3.  Créer les extracteurs nécessaires pour les sources sans RSS.
4.  Traiter les sites dynamiques, notamment l'ANAP.
5.  Fiabiliser historique et déduplication.
6.  Produire un flux global stable.
7.  Améliorer le diagnostic `status.json`.
8.  Faciliter l'ajout de nouvelles sources.

## Contraintes

-   solution gratuite autant que possible ;
-   GitHub, GitHub Actions et GitHub Pages ;
-   pas de contournement d'authentification, CAPTCHA, abonnement ou
    protection d'accès ;
-   privilégier les flux officiels lorsqu'ils existent et fonctionnent.

## Liens projet

Dépôt GitHub : `https://github.com/AbonnementsGrp/veille-rss`

Application GitHub Pages :
`https://abonnementsgrp.github.io/veille-rss/`

L'infrastructure GitHub est déjà en place. La priorité est désormais de
fiabiliser le moteur et la prise en charge des sources.
