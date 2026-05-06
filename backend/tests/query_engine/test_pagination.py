"""
Tests — pagination.py
======================

paginate_results() est une fonction pure — pas de mocks, pas d'async.
Tout le comportement est déterministe et testable sans infrastructure.

CONCEPT PRODUIT : Pourquoi paginer ?
--------------------------------------
Performance  : ne charger que N résultats, pas toute la table.
UX           : le front peut afficher "page 2 sur 11" avec des contrôles précédent/suivant.
Coût API     : réduire la taille des payloads JSON.
Cohérence    : la stratégie de pagination est centralisée ici, pas dans chaque service.

DIFFÉRENCE SQL vs Semantic/Hybrid :
--------------------------------------
SQL    : OFFSET/LIMIT natifs DB → seules les N lignes de la page traversent le réseau.
         Équivalent PHP/Doctrine : $qb->setFirstResult($offset)->setMaxResults($perPage)

Semantic/Hybrid : on récupère d'abord tous les résultats scorés,
                  puis on slice en Python.
                  Équivalent PHP : array_slice($results, $offset, $perPage)

paginate_results() implémente cette logique Python — elle n'est appelée que
pour les stratégies semantic et hybrid. Le SQL reçoit page/per_page directement.
"""

from unittest.mock import MagicMock

import pytest

from app.entities.search.pagination import paginate_results
from app.entities.search.query_types import QueryStrategy, SearchResult


class TestPaginateResults:

    def test_first_page_returns_first_n_items(self):
        items = list(range(10))
        page, total_pages = paginate_results(items, page=1, per_page=3)
        assert page == [0, 1, 2]
        assert total_pages == 4  # ceil(10/3)

    def test_middle_page_returns_correct_slice(self):
        items = list(range(10))
        page, total_pages = paginate_results(items, page=2, per_page=3)
        assert page == [3, 4, 5]
        assert total_pages == 4

    def test_last_partial_page(self):
        items = list(range(10))
        page, total_pages = paginate_results(items, page=4, per_page=3)
        assert page == [9]  # une seule valeur sur la dernière page
        assert total_pages == 4

    def test_page_beyond_end_returns_empty_list(self):
        items = list(range(5))
        page, total_pages = paginate_results(items, page=99, per_page=10)
        assert page == []
        assert total_pages == 1  # ceil(5/10) = 1

    def test_empty_list_returns_empty_page_and_total_pages_1(self):
        page, total_pages = paginate_results([], page=1, per_page=10)
        assert page == []
        assert total_pages == 1  # convention UI : toujours au moins 1 page

    def test_per_page_1_each_item_on_its_own_page(self):
        items = ["a", "b", "c"]
        p1, total = paginate_results(items, page=1, per_page=1)
        p2, _ = paginate_results(items, page=2, per_page=1)
        p3, _ = paginate_results(items, page=3, per_page=1)
        assert p1 == ["a"]
        assert p2 == ["b"]
        assert p3 == ["c"]
        assert total == 3

    def test_per_page_larger_than_list_returns_all_items(self):
        items = [1, 2, 3]
        page, total_pages = paginate_results(items, page=1, per_page=100)
        assert page == [1, 2, 3]
        assert total_pages == 1

    def test_exact_division_total_pages(self):
        items = list(range(20))
        _, total_pages = paginate_results(items, page=1, per_page=5)
        assert total_pages == 4  # 20 / 5 = 4 exact

    def test_total_pages_calculation_53_results_per_5(self):
        items = list(range(53))
        _, total_pages = paginate_results(items, page=1, per_page=5)
        assert total_pages == 11  # ceil(53/5) = 11

    def test_works_with_searchresult_objects(self):
        """paginate_results est générique — fonctionne avec tous types d'objets."""
        props = [MagicMock() for _ in range(5)]
        srs = [
            SearchResult(property=p, score=0.9, strategy=QueryStrategy.sql_only)
            for p in props
        ]
        page, total_pages = paginate_results(srs, page=2, per_page=2)
        assert len(page) == 2
        assert page[0].property == props[2]
        assert page[1].property == props[3]
        assert total_pages == 3  # ceil(5/2) = 3

    def test_order_is_preserved_after_slice(self):
        """L'ordre des résultats (score décroissant pour semantic/hybrid) est conservé."""
        items = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
        page, _ = paginate_results(items, page=2, per_page=3)
        assert page == [7, 6, 5]
