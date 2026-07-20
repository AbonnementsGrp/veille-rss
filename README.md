# Veille RSS — V2

Générateur gratuit de flux RSS hébergé sur GitHub.

## Ce que fait cette version

- utilise un flux RSS officiel lorsqu'il est renseigné ou détecté ;
- sinon tente d'extraire les actualités depuis le HTML et le JSON-LD ;
- crée un flux par source dans `public/` ;
- crée un flux consolidé `public/veille.xml` ;
- conserve un historique dans `data/history.json` ;
- produit un état de fonctionnement dans `public/status.json` ;
- s'exécute automatiquement toutes les trois heures avec GitHub Actions ;
- publie les flux avec GitHub Pages.

## Installation depuis le navigateur GitHub

1. Décompresser le ZIP sur l'ordinateur.
2. Dans le dépôt GitHub vide, cliquer sur **uploading an existing file**.
3. Glisser tout le contenu du dossier décompressé, y compris les dossiers `.github`, `config`, `data` et `public`.
4. Valider avec **Commit changes**.
5. Ouvrir **Settings > Pages** et choisir **GitHub Actions** dans **Source**.
6. Ouvrir **Actions > Générer les flux RSS > Run workflow**.

L'adresse finale du flux global sera :

```text
https://VOTRE-COMPTE.github.io/veille-rss/veille.xml
```

Le fichier `status.json` permettra de contrôler les sites en erreur :

```text
https://VOTRE-COMPTE.github.io/veille-rss/status.json
```

## Ajouter un site

Modifier `config/sites.yml` :

```yaml
- name: "Nom de la source"
  url: "https://exemple.fr/actualites"
  output: "exemple.xml"
```

Lorsqu'un flux officiel est connu :

```yaml
- name: "Nom de la source"
  url: "https://exemple.fr/actualites"
  official_feed: "https://exemple.fr/feed.xml"
  output: "exemple.xml"
```

Pour une page HTML difficile, des sélecteurs peuvent être précisés :

```yaml
selectors:
  item: ["article", ".news-card"]
  title: ["h2 a", "h3 a"]
  description: [".excerpt", "p"]
  date: ["time", ".date"]
```

## Limite importante

Les sites qui chargent leurs articles uniquement avec JavaScript, une API protégée ou une plateforme dynamique peuvent nécessiter une adaptation spécifique. L'ANAP est conservée dans la configuration, mais son bon fonctionnement devra être vérifié après la première exécution.
