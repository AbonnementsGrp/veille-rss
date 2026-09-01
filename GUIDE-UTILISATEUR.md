# Guide d'utilisation de la veille

Ce guide s'adresse à qui veut **suivre** la veille. Pour la faire évoluer — ajouter
une source, corriger un extracteur — voir le [README](README.md).

## En une minute

Onze sources d'actualité du secteur public local sont relevées **toutes les trois
heures**, réparties en cinq domaines. Chacune donne un flux RSS ; un flux global
les rassemble. Tout est publié sur une page unique :

**https://abonnementsgrp.github.io/veille-rss/**

Vous n'avez rien à installer. Il suffit d'ajouter une adresse dans un lecteur de
flux, ou de consulter la page directement.

## S'abonner

Trois façons, selon ce que vous voulez :

| Vous voulez… | Utilisez |
|---|---|
| Tout suivre dans un seul fil | le flux global `https://abonnementsgrp.github.io/veille-rss/veille.xml` |
| Garder les sources séparées, classées par domaine | le fichier OPML `https://abonnementsgrp.github.io/veille-rss/feeds.opml` |
| Une seule source | l'adresse de son flux, colonne « Flux » du tableau de bord (voir aussi la liste plus bas) |

L'**OPML** est un fichier d'abonnements : votre lecteur l'importe et crée d'un
coup les onze flux, rangés dans cinq dossiers (Enfance & Éducation, Santé, social
& séniors, Culture, Tourisme, Restauration). C'est l'option recommandée si vous
voulez pouvoir traiter les domaines séparément.

### Selon votre lecteur

Les libellés varient d'une version à l'autre ; le principe, non.

**Outlook classique (application Windows)** — *Fichier* → *Paramètres du compte*
→ *Paramètres du compte* → onglet *Flux RSS* → *Nouveau*, puis collez l'adresse
du flux. Les articles arrivent dans un dossier *Flux RSS* de votre boîte.

> À savoir : le **nouvel Outlook** et **Outlook sur le web** ne gèrent pas les
> flux RSS. Si vous ne trouvez pas l'onglet *Flux RSS*, vous êtes sur une de ces
> versions : utilisez alors Thunderbird, Feedly ou Inoreader, ou consultez
> simplement le tableau de bord.

**Thunderbird** — créez un compte de type *Flux d'actualités*, puis
*Gérer les abonnements aux flux* → *Importer* et choisissez le fichier OPML
(téléchargez-le d'abord depuis l'adresse ci-dessus). C'est le lecteur qui tire le
meilleur parti de l'OPML, dossiers compris.

**Feedly, Inoreader, NewsBlur et consorts** — cherchez *Import OPML* dans les
réglages, ou collez directement l'adresse d'un flux dans la barre de recherche
d'abonnement.

**Un simple navigateur** — la page du tableau de bord suffit : elle liste les
derniers états et donne accès à chaque flux.

## Lire le tableau de bord

La page d'accueil affiche cinq compteurs, puis un tableau des sources groupées
par domaine.

| Colonne | Ce qu'elle dit |
|---|---|
| **Source** | Le nom court. Survolez-le pour voir le nom complet. |
| **État** | `OK` si la source a répondu, `ERREUR` sinon. |
| **Articles** | Nombre d'articles publiés dans le flux de cette source. |
| **Méthode / détail** | Comment les articles ont été obtenus, et le message d'erreur le cas échéant. |
| **Flux** | Lien direct vers le flux RSS de la source. |

Sous le titre, la date de dernière génération est suivie de son ancienneté
(« il y a 2 heures »). **Au-delà de neuf heures, un bandeau orange s'affiche** :
la veille ne tourne plus normalement, et le bandeau renvoie vers l'historique des
exécutions. Ce calcul se fait dans votre navigateur, il est donc toujours à jour
même si la page, elle, ne l'est plus.

### Comprendre la colonne « Méthode »

Elle indique la solidité de la collecte, ce qui explique parfois la qualité du
résultat.

| Méthode | Ce que cela signifie pour vous |
|---|---|
| `flux officiel`, `flux détecté` | Cas idéal : le site publie un flux, tout vient de lui. |
| `repli : …` | Le flux annoncé par le site ne fonctionne pas ; les articles sont lus sur sa page d'actualités. Fiable, mais les résumés peuvent être plus courts. |
| `html_selectors`, `json_ld+html`, `generic_links` | Le site n'a pas de flux exploitable : les articles sont extraits de la page. Un titre peut être tronqué, une date manquer. |
| `plan de site` | Le site est entièrement en JavaScript : seules les adresses et les dates sont disponibles. Titres approximatifs, pas de résumé. C'est le cas de l'ANAP. |
| `historique conservé` | La source est momentanément injoignable ; son dernier contenu connu reste publié. Rien ne disparaît, mais rien de neuf n'arrive. |
| `échec` | La source est injoignable et rien n'était connu d'elle. |

## Les sources suivies

Les nombres d'articles évoluent à chaque collecte.

### Enfance & Éducation

| Source | Ce qu'elle couvre | Flux |
|---|---|---|
| **Enfance & Jeunesse Infos** | Veille juridique du secteur enfance-jeunesse : décrets, circulaires, jurisprudence | `enfance-jeunesse-veille-juridique.xml` |
| **Pros de la petite enfance** | Actualité professionnelle de la petite enfance : métiers, structures, études | `pros-petite-enfance.xml` |
| **Localtis — Jeunesse** | Jeunesse, éducation et formation vues du côté des collectivités | `localtis-jeunesse-education-formation.xml` |

### Santé, social & séniors

| Source | Ce qu'elle couvre | Flux |
|---|---|---|
| **CNSA** | Autonomie, handicap, grand âge : financements, appels à projets, nominations | `cnsa.xml` |
| **Localtis — Publics fragiles** | Publics fragiles côté collectivités | `localtis-publics-fragiles.xml` |
| **IGAS** | Rapports et actualités de l'Inspection générale des affaires sociales | `igas.xml` |
| **ANAP** | Ressources et publications sur la performance des établissements sanitaires et médico-sociaux | `anap.xml` |

### Culture, Tourisme, Restauration

| Source | Ce qu'elle couvre | Flux |
|---|---|---|
| **Observatoire de la culture** | Politiques culturelles territoriales | `observatoire-culture.xml` |
| **ADN Tourisme** | Fédération des organismes institutionnels de tourisme | `adn-tourisme.xml` |
| **C2L Solutions** | Restauration collective : marchés, réglementation, EGalim | `c2l-restauration-collective.xml` |
| **SNRC** | Syndicat national de la restauration collective | `snrc.xml` |

Chaque flux s'obtient en préfixant son nom de fichier par
`https://abonnementsgrp.github.io/veille-rss/`.

## Questions fréquentes

**À quelle vitesse un nouvel article apparaît-il ?**
Trois heures au plus dans le cas courant. Le planificateur GitHub décale parfois
les exécutions de plusieurs heures ; c'est précisément ce que signale le bandeau
d'ancienneté du tableau de bord.

**Une source est en `ERREUR` mais des articles s'affichent quand même. Normal ?**
Oui. Quand une source devient injoignable, son dernier contenu connu reste
publié plutôt que de disparaître. L'état signale qu'il n'y a rien de neuf, pas
que tout est perdu.

**Certains articles n'ont pas de résumé.**
C'est le cas des articles de l'ANAP : son site étant rendu en JavaScript, aucun
résumé n'est accessible. Ailleurs, quand le flux d'un site n'en fournit pas, le
résumé est lu sur la page de l'article — mais cela prend quelques cycles pour se
compléter après l'ajout d'une source.

**Des titres ANAP sont bizarres (« Webinaire rdv transfo »).**
Ils sont déduits de l'adresse de la page, faute d'autre information disponible.
Quand l'adresse est explicite, le titre l'est aussi ; quand elle est laconique,
le titre l'est également.

**Le même article peut-il apparaître deux fois ?**
Non, deux garde-fous l'évitent : les adresses sont normalisées (paramètres de
suivi retirés) et un même titre n'est publié qu'une fois par source. C'est utile
car plusieurs sites publient réellement leurs articles sous deux adresses.

**Une source ne publie plus rien depuis longtemps.**
Cela peut venir de la source elle-même. C'est le cas de *Localtis — Publics
fragiles* : la rubrique n'a rien publié depuis avril 2024, alors que son flux
fonctionne.

**Combien d'articles sont conservés ?**
Soixante au maximum par source, mille pour l'ensemble. Les plus anciens sortent
au fur et à mesure.

**Puis-je demander l'ajout d'une source ?**
Oui : ouvrez une *issue* sur le [dépôt](https://github.com/AbonnementsGrp/veille-rss/issues)
en indiquant l'adresse de la page d'actualités. Il n'est pas nécessaire qu'elle
dispose d'un flux RSS.

**Un flux ne se met plus à jour dans mon lecteur.**
Comparez d'abord avec le tableau de bord. Si la page est à jour et votre lecteur
non, videz son cache d'abonnement ou réimportez le flux. Si la page elle-même
affiche le bandeau orange, le problème est en amont.

## Signaler un problème

Les erreurs visibles au tableau de bord sont généralement transitoires : une
source indisponible se rétablit d'elle-même à l'exécution suivante. Si une source
reste en erreur plusieurs jours, ou si un flux publie des titres manifestement
faux, ouvrez une
[issue](https://github.com/AbonnementsGrp/veille-rss/issues) en précisant la
source et ce que vous observez.
