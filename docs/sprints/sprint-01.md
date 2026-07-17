# Sprint 1 — Ingestion Vélib complète et idempotente

## Objectif

Remplacer l’ingestion limitée à 100 stations par une ingestion complète,
robuste et historisée de toutes les stations Vélib exposées par l’API
Paris Open Data.

## Fonctionnement

Le pipeline appelle l’API avec les paramètres suivants :

- `limit=100` ;
- pagination avec `offset` ;
- tri stable avec `order_by=stationcode` ;
- timeout HTTP de 30 secondes ;
- trois retries avec backoff ;
- retry sur les statuts 429, 500, 502, 503 et 504.

Le tri par `stationcode` est indispensable. Sans ordre explicite, un test
réel a récupéré seulement 1 421 observations uniques sur les 1 516
annoncées par l’API.

## Validation

Chaque réponse doit contenir :

- un `total_count` entier positif ou nul ;
- une liste `results` ;
- un `stationcode` pour chaque station ;
- un horodatage métier `duedate`.

Une page vide avant d’atteindre `total_count` provoque l’échec du run afin
d’éviter une ingestion partielle silencieuse.

## Idempotence

La clé métier d’une observation est :

```text
(stationcode, last_reported)