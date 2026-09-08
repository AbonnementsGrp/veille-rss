"""L'article : identité fixée à la création, indépendante des corrections de titre."""

from __future__ import annotations

from dataclasses import asdict

from veille.history import history_items_for_source
from veille.models import Item


class TestIdentite:
    def test_deux_articles_identiques_partagent_leur_identite(self):
        a = Item("S", "Un titre", "https://exemple.fr/a?utm_source=x")
        b = Item("S", "Un titre", "https://exemple.fr/a")
        assert a.uid == b.uid, "le lien est normalisé avant le calcul"

    def test_l_identite_survit_a_la_correction_du_titre(self):
        item = Item("ANAP", "Webinaire rdv transfo", "https://exemple.fr/s/article/webinaire-rdv-transfo")
        avant = item.uid
        item.title = "Webinaire : les rendez-vous de la transformation"
        assert item.uid == avant, "un titre lu sur la page ne fait pas un nouvel article ni un nouveau guid"
        assert item.compute_uid() != avant, "recalculée, l'identité changerait : elle ne l'est jamais"

    def test_l_identite_peut_etre_imposee(self):
        item = Item("S", "Titre corrigé", "https://exemple.fr/a")
        item.uid = "identite-enregistree"
        assert item.uid == "identite-enregistree"

    def test_l_identite_n_entre_ni_dans_asdict_ni_dans_l_egalite(self):
        a = Item("S", "T", "https://exemple.fr/a")
        b = Item("S", "T", "https://exemple.fr/a")
        b.uid = "autre"
        assert "_uid" not in asdict(a)
        assert a == b


class TestHistoriqueEtIdentite:
    def test_l_article_reconstruit_depuis_l_historique_garde_l_identite_enregistree(self):
        ebauche = Item("ANAP", "Webinaire rdv transfo", "https://exemple.fr/s/article/webinaire-rdv-transfo")
        history = {
            ebauche.uid: {
                "uid": ebauche.uid, "source": "ANAP", "link": ebauche.link,
                "title": "Webinaire : les rendez-vous de la transformation", "title_enriched": True,
                "first_seen": "2026-09-01T08:00:00+00:00",
            },
        }
        [item] = history_items_for_source(history, "ANAP", 10)
        assert item.title == "Webinaire : les rendez-vous de la transformation"
        assert item.uid == ebauche.uid

    def test_un_enregistrement_sans_identite_en_recalcule_une(self):
        history = {"x": {"source": "S", "link": "https://exemple.fr/a", "title": "T", "first_seen": "2026-09-01T08:00:00+00:00"}}
        [item] = history_items_for_source(history, "S", 10)
        assert item.uid == Item("S", "T", "https://exemple.fr/a").uid
