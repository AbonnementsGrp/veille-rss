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
| Une seule source | colonne « Activité » du tableau de bord pour le flux produit par la veille ; colonne « Flux » pour le flux brut publié par le site (voir aussi la liste plus bas) |

L'**OPML** est un fichier d'abonnements : votre lecteur l'importe et crée d'un
coup les onze flux, rangés dans cinq dossiers (Culture, Enfance & Éducation,
Restauration, Santé, social & séniors, Tourisme). C'est l'option recommandée si vous
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

La page d'accueil affiche six compteurs, puis un tableau des sources groupées
par domaine. Domaines et sources y sont classés par ordre alphabétique ; les
sources sans domaine sont regroupées en dernier sous « Autres ».

À gauche du tableau, un **sommaire des domaines** reste visible pendant le
défilement : cliquez un domaine pour arriver directement sur sa rubrique, qui se
surligne un instant. Chaque entrée indique le nombre de sources du domaine ; un
⚠ rouge signale qu'au moins une source est en erreur, un ⚠ orange qu'une source
est à surveiller (voir la colonne État). Un domaine qui vient d'être créé et n'a
encore aucune source y figure en gris, à zéro, sans rubrique dans le tableau :
il n'en aura une qu'à sa première source. Sur un écran étroit, ce sommaire passe
au-dessus du tableau.

| Colonne | Ce qu'elle dit |
|---|---|
| **Source** | Le nom court. Survolez-le pour voir le nom complet. |
| **État** | `OK` si la source a répondu, `ERREUR` sinon. Un ⚠ orange à côté de `OK` signale une source **à surveiller** : elle répond, mais rien de neuf n'est paru depuis plus de deux mois, ou les articles extraits ont l'air douteux (titres de menu, dates absentes ou dans le futur). Survolez le ⚠ ; le détail est aussi écrit dans la dernière colonne. |
| **Articles** | Nombre d'articles publiés dans le flux de cette source. |
| **Flux** | L'adresse du flux RSS que le site publie lui-même, en clair, avec un bouton **Copier**. « pas de flux publié » signifie que le site n'en publie pas d'exploitable : la veille l'a lu sur sa page ou son plan de site, utilisez alors la colonne Activité. La mention « filtré : … » indique que la veille ne garde de ce flux qu'une catégorie ; un abonnement direct à l'adresse recevrait tout le site. |
| **Activité** | Lien vers le flux RSS produit par la veille pour cette source : articles dédoublonnés, résumés complétés, historique conservé. |
| **Méthode / détail** | Comment les articles ont été obtenus. En cas d'erreur, un résumé en quelques mots ; cliquez dessus pour lire le message technique complet. |

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
| `plan de site` | Le site est entièrement en JavaScript : les adresses et les dates viennent de son plan de site, puis un navigateur lit chaque page d'article pour en tirer le titre et le résumé. Les tout derniers articles peuvent garder quelques heures un titre approximatif, le temps de cette lecture. C'est le cas de l'ANAP. |
| `navigateur : …` | La page du site n'affiche ses articles qu'une fois son code exécuté : un navigateur la rend avant l'extraction. Même fiabilité qu'une extraction de page, collecte un peu plus lente. |
| `historique conservé` | La source est momentanément injoignable ; son dernier contenu connu reste publié. Rien ne disparaît, mais rien de neuf n'arrive. |
| `échec` | La source est injoignable et rien n'était connu d'elle. |

## Les sources suivies

Les nombres d'articles évoluent à chaque collecte.

### Culture

| Source | Ce qu'elle couvre | Flux |
|---|---|---|
| **Observatoire de la culture** | Politiques culturelles territoriales | `observatoire-culture.xml` |

### Enfance & Éducation

| Source | Ce qu'elle couvre | Flux |
|---|---|---|
| **Enfance & Jeunesse Infos** | Veille juridique du secteur enfance-jeunesse : décrets, circulaires, jurisprudence | `enfance-jeunesse-veille-juridique.xml` |
| **Localtis — Jeunesse** | Jeunesse, éducation et formation vues du côté des collectivités | `localtis-jeunesse-education-formation.xml` |
| **Pros de la petite enfance** | Actualité professionnelle de la petite enfance : métiers, structures, études | `pros-petite-enfance.xml` |

### Restauration

| Source | Ce qu'elle couvre | Flux |
|---|---|---|
| **C2L Solutions** | Restauration collective : marchés, réglementation, EGalim | `c2l-restauration-collective.xml` |
| **SNRC** | Syndicat national de la restauration collective | `snrc.xml` |

### Santé, social & séniors

| Source | Ce qu'elle couvre | Flux |
|---|---|---|
| **ANAP** | Ressources et publications sur la performance des établissements sanitaires et médico-sociaux | `anap.xml` |
| **CNSA** | Autonomie, handicap, grand âge : financements, appels à projets, nominations | `cnsa.xml` |
| **IGAS** | Rapports et actualités de l'Inspection générale des affaires sociales | `igas.xml` |
| **Localtis — Publics fragiles** | Publics fragiles côté collectivités | `localtis-publics-fragiles.xml` |

### Tourisme

| Source | Ce qu'elle couvre | Flux |
|---|---|---|
| **ADN Tourisme** | Fédération des organismes institutionnels de tourisme | `adn-tourisme.xml` |

Chaque flux s'obtient en préfixant son nom de fichier par
`https://abonnementsgrp.github.io/veille-rss/`.

## Proposer une source

Vous connaissez un site qui mériterait d'être suivi ? Il suffit d'un compte GitHub,
aucune manipulation technique.

1. Ouvrez le formulaire : bouton **Proposer une source** sur le tableau de bord,
   ou directement
   https://github.com/AbonnementsGrp/veille-rss/issues/new?template=nouvelle-source.yml
2. Indiquez l'**adresse de la page d'actualités** du site — la page qui liste les
   articles, pas la page d'accueil — et choisissez le **domaine**. Le nom est
   facultatif : il est proposé d'après le site si vous le laissez vide. Si aucun
   domaine de la liste ne convient, proposez d'abord le domaine (voir plus bas),
   puis la source.
3. Envoyez. Dans les minutes qui suivent, un commentaire automatique apparaît
   sous votre demande avec le résultat de l'enquête :

| En tête du commentaire | Ce que cela veut dire |
|---|---|
| ✅ Source prête à être ajoutée | Un flux ou une liste d'articles propre a été trouvée. Il ne manque que la validation. |
| ⚠️ Exploitable, à vérifier | Des articles ont été trouvés, mais avec des réserves — dates manquantes, méthode fragile, adresse déjà suivie, ou page en JavaScript qu'il a fallu ouvrir dans un navigateur pour voir les articles. Lisez l'aperçu : s'il montre des liens de menu plutôt que des articles, proposez une autre page du site. |
| ❌ Demande un réglage manuel | La page ne se laisse pas lire automatiquement, même ouverte dans un navigateur (structure inhabituelle, liste d'articles absente). Un responsable devra intervenir à la main, ou une autre page peut être tentée. |

   Le commentaire montre les cinq premiers articles trouvés : c'est le meilleur
   moyen de juger si la source est la bonne.
4. Un responsable valide en posant l'étiquette **approuvé**. La source est alors
   ajoutée automatiquement, votre demande est fermée, et elle apparaît sur le
   tableau de bord à la génération suivante.

Pour corriger le nom ou le domaine après coup, modifiez simplement votre demande
(bouton *Edit* sur le premier message) : l'enquête est relancée et un nouveau
commentaire s'ajoute sous le précédent.

## Proposer un domaine

Les domaines sont les rubriques du tableau de bord : Enfance & Éducation, Santé,
social & séniors, Culture, Tourisme, Restauration. Pour en créer un :

1. Ouvrez le formulaire : bouton **Proposer un domaine** sur le tableau de bord,
   ou directement
   https://github.com/AbonnementsGrp/veille-rss/issues/new?template=nouveau-domaine.yml
2. Donnez son **nom**, court et lisible. Il prendra sa place alphabétique parmi
   les domaines existants.
3. Un commentaire automatique montre la liste des domaines qui en résulterait, ou
   explique le refus (nom déjà pris, trop long).
4. Un responsable pose l'étiquette **approuvé** : le domaine est créé et apparaît
   aussitôt dans la liste proposée au moment d'ajouter une source. Il ne
   s'affiche sur le tableau de bord qu'une fois qu'une source lui est rattachée.

## Renommer un domaine

Ouvrez le formulaire **Renommer un domaine** (lien sur le tableau de bord, ou
https://github.com/AbonnementsGrp/veille-rss/issues/new?template=renommer-domaine.yml),
indiquez le domaine actuel — tel qu'il s'affiche, casse et accents sans importance —
et le nouveau nom. Le commentaire automatique montre le domaine reconnu, les
sources concernées et la liste qui en résulte. Après validation par un responsable,
le nouveau nom est en place partout : tableau de bord, dossiers de l'OPML, liste
proposée à l'ajout d'une source.

## Supprimer un domaine

Ouvrez le formulaire **Supprimer un domaine** (lien sur le tableau de bord, ou
https://github.com/AbonnementsGrp/veille-rss/issues/new?template=supprimer-domaine.yml)
et donnez le nom du domaine tel qu'il s'affiche. **Ses sources ne sont pas
supprimées** : indiquez le domaine qui doit les accueillir, ou laissez le champ
vide pour qu'elles passent sous « Autres ». Le commentaire automatique montre le
domaine reconnu, les sources concernées et leur destination. Après validation
par un responsable, la rubrique disparaît du tableau de bord, des dossiers de
l'OPML et de la liste proposée à l'ajout d'une source. Le dernier domaine ne
peut pas être supprimé.

## Supprimer une source

Ouvrez le formulaire **Supprimer une source** (lien sur le tableau de bord, ou
https://github.com/AbonnementsGrp/veille-rss/issues/new?template=supprimer-source.yml)
et donnez le nom de la source tel qu'il s'affiche. Le commentaire automatique
récapitule ce qui sera retiré : la source reconnue, son domaine, son flux publié
et le nombre d'articles de son historique. **La suppression est irréversible** :
lisez ce récapitulatif avant de valider. Après validation, la source disparaît du
tableau de bord et de l'OPML à la génération suivante ; les lecteurs abonnés à
son flux ne recevront plus rien.

## Valider une demande (responsables)

Toutes les demandes — source, domaine, renommage, suppression — s'appliquent de
la même façon : un responsable pose l'étiquette **approuvé** sur l'issue. Rien
ne se passe tant qu'elle n'est pas posée ; l'automate se contente d'écrire son
récapitulatif en commentaire.

1. Ouvrez l'issue (le mail de notification contient le lien, sinon onglet
   *Issues* du dépôt https://github.com/AbonnementsGrp/veille-rss/issues).
2. Lisez le dernier commentaire automatique : c'est exactement ce qui sera fait.
3. Dans la colonne de droite, cliquez sur le rouage à côté de **Labels**, cochez
   **approuvé** (tapez `appr` pour la trouver), puis cliquez n'importe où pour
   refermer la liste. Sur téléphone, les étiquettes sont dans le menu « … » de
   l'issue.
4. En une à deux minutes, l'automate applique la demande, ajoute un commentaire
   de confirmation (« Domaine ajouté », « Source supprimée »…) et **ferme
   l'issue**. Le tableau de bord suit à la génération suivante, au plus tard
   trois heures après.

Pour **refuser** une demande, ne posez pas l'étiquette : fermez simplement
l'issue (bouton *Close issue* sous les commentaires). Pour la corriger, modifiez
le formulaire du premier message : la vérification est relancée. Si l'automate
n'a pas pu appliquer une demande approuvée, il le dit en commentaire et retire
lui-même l'étiquette.

Il faut être **collaborateur du dépôt** pour poser une étiquette : si le rouage
n'apparaît pas à côté de *Labels*, votre compte n'a pas ce droit. Le compte
propriétaire du dépôt (AbonnementsGrp) l'a ; il peut donner ce droit à un autre
compte dans *Settings* → *Collaborators* du dépôt (le rôle *Triage* suffit).

## Questions fréquentes

**À quelle vitesse un nouvel article apparaît-il ?**
Trois heures au plus dans le cas courant. Le planificateur GitHub décale parfois
les exécutions de plusieurs heures ; c'est précisément ce que signale le bandeau
d'ancienneté du tableau de bord.

**Une source est en `ERREUR` mais des articles s'affichent quand même. Normal ?**
Oui. Quand une source devient injoignable, son dernier contenu connu reste
publié plutôt que de disparaître. L'état signale qu'il n'y a rien de neuf, pas
que tout est perdu.

**Une source est `OK` mais porte un ⚠ orange.**
Elle répond, mais la veille a remarqué quelque chose : rien de neuf depuis plus
de deux mois, des titres qui ressemblent à des liens de menu, des articles sans
date ou datés dans le futur. Le détail est écrit sous la méthode, dans la
dernière colonne. Le plus souvent, le site a simplement cessé de publier — la
rubrique « Publics fragiles » de Localtis est dans ce cas depuis 2024. Si la
source vous paraît cassée, signalez-le (voir « Signaler un problème »).

**Certains articles n'ont pas de résumé.**
Quand le flux d'un site n'en fournit pas, le résumé est lu sur la page de
l'article — au rythme d'une vingtaine de pages par exécution, cela prend
quelques cycles pour se compléter après l'ajout d'une source. Pour l'ANAP, dont
le site est rendu en JavaScript, cette lecture passe par un navigateur : même
principe, même délai.

**Un titre ANAP est bizarre (« Webinaire rdv transfo »).**
Tant que la page d'un article n'a pas été lue, son titre est déduit de son
adresse. Le vrai titre le remplace dès la lecture, en général dans les heures
qui suivent la parution.

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
Oui, par le formulaire décrit plus haut : une adresse et un domaine suffisent, et
le résultat de l'enquête vous est montré avant toute validation. Il n'est pas
nécessaire que le site dispose d'un flux RSS.

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
