# Sprint 3 — Modèles dbt incrémentaux

## Objectif

Séparer le référentiel courant des stations de l’historique de leur
disponibilité et éviter la reconstruction complète de la table de faits.

## Grain des modèles

### `dim_stations`

Une ligne représente une station Vélib dans son état descriptif le plus
récemment ingéré.

Clé unique :

```text
station_id