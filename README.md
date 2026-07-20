# Veille RSS

Générateur automatique de flux RSS hébergé gratuitement sur GitHub.

## Fonctions incluses

- utilisation prioritaire des flux RSS/Atom officiels ;
- découverte automatique d'un flux officiel ;
- extraction HTML avec sélecteurs configurables ;
- extraction de données JSON-LD ;
- détection générique des liens d'actualités ;
- conservation de l'historique ;
- maintien du précédent flux lorsqu'une source est temporairement en erreur ;
- flux individuel pour chaque source ;
- flux consolidé `veille.xml` ;
- tableau de bord `index.html` ;
- état machine lisible `status.json` ;
- fichier OPML `feeds.opml` ;
- exécution automatique toutes les trois heures.

## Ajouter une source

Modifier `config/sites.yml`, puis ajouter :

```yaml
- name: "Nom de la source"
  url: "https://exemple.fr/actualites"
  output: "exemple.xml"
```

Pour une page difficile, ajouter des sélecteurs CSS :

```yaml
  selectors:
    item: ["article", ".card"]
    title: ["h2 a", "h3 a"]
    description: [".summary", "p"]
    date: ["time", ".date"]
```

## Adresses publiées

- tableau de bord : `https://abonnementsgrp.github.io/veille-rss/`
- flux global : `https://abonnementsgrp.github.io/veille-rss/veille.xml`
- état : `https://abonnementsgrp.github.io/veille-rss/status.json`
- liste OPML : `https://abonnementsgrp.github.io/veille-rss/feeds.opml`
