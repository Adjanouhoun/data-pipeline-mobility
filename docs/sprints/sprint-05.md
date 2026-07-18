# Sprint 5 — Optimisation PostgreSQL

## Objectif

Optimiser les accès PostgreSQL utilisés par les modèles dbt et les futurs
tableaux de bord Superset, tout en préparant une politique de rétention
compatible avec les ressources du VPS.

Configuration cible actuelle :

- 4 vCores ;
- 8 Go de RAM, avec passage prévu à 16 Go ;
- 75 Go de stockage ;
- quatre projets indépendants destinés à partager la même VM.

## État initial

Avant ce sprint, les tables analytiques dbt ne possédaient aucun index
physique.

La table RAW possédait les index suivants :

- un index unique sur `stationcode` et `last_reported` ;
- un index sur `ingested_at`.

L’ancien index simple sur `stationcode` a été supprimé, car il était redondant
avec la première colonne de l’index unique composite.

## Requêtes analysées

### Historique d’une station

La requête suivante représente l’affichage de l’historique d’une station dans
Superset :

```sql
select
    station_id,
    status_updated_at,
    bikes_available,
    docks_available
from schema_analytics.fct_velib_status
where station_id = '8028'
order by status_updated_at desc
limit 100;
```

Avant indexation, PostgreSQL effectuait un parcours séquentiel complet de la
table :

```text
Seq Scan
Rows Removed by Filter: 3523
Execution Time: 0.281 ms
```

Après indexation :

```text
Index Scan Backward
Execution Time: 0.070 ms
```

Le temps d’exécution mesuré a diminué d’environ 75 % sur la volumétrie locale.

### Dernières observations

La requête suivante représente l’affichage des dernières observations, toutes
stations confondues :

```sql
select
    station_id,
    status_updated_at,
    bikes_available,
    docks_available
from schema_analytics.fct_velib_status
order by status_updated_at desc
limit 100;
```

Avant indexation :

```text
Seq Scan
Sort Method: top-N heapsort
Execution Time: 1.587 ms
```

Après indexation :

```text
Index Scan Backward
Execution Time: 0.152 ms
```

Le temps d’exécution mesuré a diminué d’environ 90 % sur la volumétrie locale.

Ces résultats ne constituent pas un benchmark de charge complet. Ils
confirment toutefois que PostgreSQL utilise les nouveaux index pour les
principaux chemins d’accès attendus.

## Index dbt ajoutés

### Table de faits

Le modèle `fct_velib_status` gère désormais les index suivants :

```text
UNIQUE (observation_id)
(station_id, status_updated_at)
(status_updated_at)
```

L’index unique sur `observation_id` garantit physiquement l’unicité des
observations.

L’index composite accélère la consultation chronologique de l’historique
d’une station.

L’index temporel accélère les recherches globales sur les observations les
plus récentes et les filtres temporels des tableaux de bord.

### Dimension des stations

Le modèle `dim_stations` gère désormais l’index suivant :

```text
UNIQUE (station_id)
```

Cet index garantit qu’une station ne possède qu’une seule ligne courante dans
la dimension. Il accélère également les recherches et les jointures avec la
table de faits.

Les noms physiques des index sont générés automatiquement par dbt.

## Création des index

Les index sont déclarés directement dans les configurations des modèles dbt.
Ils restent ainsi versionnés avec les tables auxquelles ils appartiennent.

La table de faits existante a été reconstruite une fois avec :

```bash
dbt run --full-refresh --select fct_velib_status
```

La dimension, matérialisée en table, a ensuite été reconstruite normalement.

Les exécutions incrémentales suivantes conservent les index existants.

## Volumétrie après indexation

Mesure locale après le Sprint 5 :

| Table | Lignes estimées | Table | Index | Total |
|---|---:|---:|---:|---:|
| `fct_velib_status` | 3 528 | 648 kB | 424 kB | 1 112 kB |
| `stg_raw_stations` | 3 528 | 536 kB | 184 kB | 760 kB |
| `dim_stations` | 1 516 | 184 kB | 56 kB | 280 kB |
| `ingestion_runs` | 1 | 8 kB | 48 kB | 64 kB |

Avec environ 1 516 stations collectées chaque heure, le pipeline peut produire
approximativement :

- 36 384 observations par jour ;
- 1,1 million d’observations par mois ;
- 13,3 millions d’observations par an.

La taille réelle dépendra de l’évolution du nombre de stations, des index, du
remplissage des pages PostgreSQL et de la maintenance de la base.

## Politique de rétention cible

La politique envisagée pour le déploiement est :

| Données | Rétention cible |
|---|---:|
| RAW détaillé | 30 jours |
| Historique analytique horaire | 12 à 24 mois |
| Agrégats quotidiens | Longue durée |
| Monitoring des ingestions | 12 mois |
| Dimension des stations | État courant |

Cette politique n’est pas encore automatisée.

## Précaution concernant le RAW

La table `fct_velib_status` est actuellement reconstruite à partir de la table
RAW lors d’un `dbt run --full-refresh`.

Supprimer les données RAW de plus de 30 jours rendrait impossible une
reconstruction complète de l’historique analytique à partir de PostgreSQL
seul.

Aucune suppression automatique ne sera donc activée avant la mise en place
des éléments suivants :

1. un modèle d’agrégation quotidienne ;
2. une sauvegarde PostgreSQL testée ;
3. une procédure de restauration documentée ;
4. une décision explicite sur la durée de conservation détaillée ;
5. une protection contre les `full-refresh` non maîtrisés.

## Validation

Résultat de la validation dbt :

```text
Modèles : succès
Tests : 36 réussis, 1 avertissement, 0 erreur
Fraîcheur de la source RAW : succès
```

L’avertissement correspond au test métier contrôlant les observations pour
lesquelles le nombre de vélos disponible dépasse temporairement la capacité
annoncée par l’API. Il reste configuré en avertissement afin de conserver et
surveiller ces anomalies provenant de la source.

## Fichiers concernés

Fichiers modifiés :

- `dbt_mobility/models/marts/fct_velib_status.sql` ;
- `dbt_mobility/models/marts/dim_stations.sql`.

Fichier créé :

- `docs/sprints/sprint-05.md`.

Aucune migration destructive et aucune suppression de données ne sont
incluses dans ce sprint.

## Suite

Les prochaines optimisations liées au stockage seront réalisées dans un
sprint distinct :

- création d’agrégats quotidiens ;
- sauvegarde et restauration PostgreSQL ;
- automatisation contrôlée de la rétention ;
- suivi de la croissance des tables et des index ;
- maintenance PostgreSQL ;
- limites de ressources Docker adaptées au VPS.