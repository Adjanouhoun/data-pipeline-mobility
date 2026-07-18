# Sprint 4 — Observabilité du pipeline

## Objectif

Enregistrer des métriques fiables pour chaque ingestion Vélib et les
rendre disponibles pour les diagnostics et les futurs dashboards
Superset.

## Architecture

Le DAG exécute désormais quatre étapes :

```text
Initialisation RAW
        ↓
Initialisation monitoring
        ↓
Ingestion Vélib et métriques
        ↓
Fraîcheur, modèles et tests dbt
```

## Table de monitoring

La table suivante est créée dans PostgreSQL :

```text
schema_monitoring.ingestion_runs
```

Une ligne représente une exécution de la tâche d’ingestion.

Les métriques enregistrées sont :

- identifiant du run Airflow ;
- identifiant du DAG ;
- identifiant de la tâche ;
- date et heure de début ;
- date et heure de fin ;
- statut `success` ou `failed` ;
- nombre de pages API ;
- volume annoncé par l’API ;
- volume reçu ;
- lignes insérées ;
- doublons ignorés ;
- durée ;
- message d’erreur éventuel.

## Gestion des erreurs

Une exécution réussie enregistre toutes ses métriques.

En cas d’échec :

- le statut devient `failed` ;
- le message d’erreur est enregistré ;
- l’erreur initiale est relancée dans Airflow ;
- un échec secondaire du monitoring ne masque pas l’erreur principale.

## Migrations SQL

La création des tables et des index a été retirée du code Python.

Les migrations sont versionnées dans :

```text
sql/001_raw_schema.sql
sql/002_monitoring_schema.sql
```

Le dossier `sql/` est monté en lecture seule dans les conteneurs Airflow :

```text
./sql:/opt/airflow/sql:ro
```

Le DAG initialise les schémas avec deux tâches dédiées avant l’ingestion.

## Index PostgreSQL

Les index suivants sont utilisés :

- index unique sur `(stationcode, last_reported)` ;
- index sur `ingested_at` pour les chargements incrémentaux ;
- index sur la date de début des exécutions ;
- index sur le statut et la date de début.

L’index simple sur `stationcode` est supprimé, car l’index composite unique
commence déjà par cette colonne.

## Vue analytique

Le modèle dbt suivant prépare les données pour Superset :

```text
schema_analytics.fct_ingestion_runs
```

Il calcule notamment :

- le débit en observations par seconde ;
- le taux de doublons ;
- un indicateur booléen de succès.

## Résultat du test complet

```text
run_id=manual__2026-07-18T00:00:00+00:00
status=success
pages_fetched=16
reported_total=1516
records_received=1516
records_inserted=0
duplicates_ignored=1516
duration_seconds=1.802
records_per_second=841.29
duplicate_rate_percent=100.00
is_success=true
```

Le taux de doublons de 100 % est attendu pour une relance idempotente
sans nouvelle donnée métier.

## Tests

Résultats :

```text
Python: 11 tests réussis
dbt: 36 réussis, 1 avertissement, 0 erreur
Airflow DAG complet: success
Source freshness: success
```

L’avertissement dbt correspond aux anomalies réelles où le nombre de
vélos est légèrement supérieur à la capacité déclarée.

## Requêtes de diagnostic

### Dernières exécutions

```sql
select *
from schema_analytics.fct_ingestion_runs
order by started_at desc
limit 20;
```

### Exécutions en échec

```sql
select *
from schema_analytics.fct_ingestion_runs
where not is_success
order by started_at desc;
```

### Durée moyenne

```sql
select
    avg(duration_seconds) as average_duration_seconds
from schema_analytics.fct_ingestion_runs;
```

### Taux de succès

```sql
select
    round(
        avg(is_success::integer) * 100,
        2
    ) as success_rate_percent
from schema_analytics.fct_ingestion_runs;
```

## Futur dashboard Superset

Le dashboard de monitoring pourra afficher :

- taux de succès ;
- durée moyenne ;
- volumes reçus et insérés ;
- taux de doublons ;
- fraîcheur de la dernière ingestion ;
- débit en observations par seconde ;
- détail des dernières erreurs.

## Limites connues à la fin du sprint

- une seule exécution est disponible immédiatement après le premier test ;
- les tendances seront significatives après plusieurs runs horaires ;
- la clé Fernet Airflow reste à configurer ;
- aucune alerte externe n’est encore envoyée ;
- la politique de rétention PostgreSQL reste à définir.