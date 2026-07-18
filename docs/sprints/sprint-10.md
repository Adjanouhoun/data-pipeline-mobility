# Sprint 10 — Dashboard Superset de monitoring

## Objectif

Créer un premier tableau de bord Superset permettant de suivre
la santé, les performances et les volumes des pipelines Vélib
et trafic routier depuis une vue analytique unique.

## Migration des métadonnées Superset

Superset utilisait initialement une base SQLite locale :

```text
/app/superset_home/superset.db
```

Cette configuration n’était pas adaptée à la conservation fiable
des dashboards et des connexions.

Superset utilise désormais PostgreSQL :

```text
Service : postgres_superset
Base : superset
```

La connexion est définie dans :

```text
superset_config.py
```

avec la variable d’environnement :

```text
SUPERSET_DATABASE_URI
```

Les migrations Superset ont été appliquées avec :

```bash
superset db upgrade
```

Les rôles et permissions ont été initialisés avec :

```bash
superset init
```

Un nouvel administrateur a été créé dans PostgreSQL.

Les deux anciens dashboards SQLite, l’ancienne connexion et l’ancien
utilisateur n’ont pas été migrés, conformément à la décision de
repartir sur une installation propre.

L’ancien fichier SQLite a ensuite été supprimé.

## Configuration Superset

Le fichier suivant est monté en lecture seule dans le conteneur :

```text
superset_config.py
```

Il configure :

- la clé secrète depuis l’environnement ;
- la base PostgreSQL de métadonnées ;
- la clé Mapbox optionnelle ;
- la page des dashboards comme page d’accueil ;
- la protection CSRF.

Le rôle public n’hérite pas automatiquement du rôle Gamma afin
d’éviter de donner des permissions excessives aux visiteurs anonymes.

## Vue dbt unifiée

Le dashboard repose sur :

```text
schema_analytics.fct_pipeline_runs
```

Cette vue réunit :

```text
schema_analytics.fct_ingestion_runs
schema_analytics.fct_traffic_ingestion_runs
```

Grain :

```text
une ligne par exécution de pipeline
```

Pipelines disponibles :

```text
Vélib
Trafic routier
```

Métriques exposées :

- identifiant du pipeline ;
- identifiant du run Airflow ;
- début et fin ;
- statut ;
- observations reçues ;
- observations insérées ;
- observations mises à jour ;
- observations inchangées ou ignorées ;
- volume modifié ;
- durée ;
- débit de traitement ;
- taux de données inchangées ;
- message d’erreur ;
- indicateur de succès.

## Connexion analytique

Connexion Superset :

```text
Mobility Warehouse
```

Base :

```text
mobility_warehouse
```

Dataset :

```text
schema_analytics.fct_pipeline_runs
```

Les horodatages `started_at` et `finished_at` sont déclarés comme
colonnes temporelles dans Superset.

## Dashboard

Nom :

```text
Monitoring de la plateforme
```

Le dashboard ne contient pas de carte géographique, car il surveille
des métriques techniques. Les cartes seront réservées aux dashboards
Vélib, trafic routier et à la future vue d’ensemble Mobilité.

## KPI

### Taux de succès

Mesure le pourcentage d’exécutions terminées avec succès.

```sql
round(
    100.0
    * sum(
        case
            when is_success then 1
            else 0
        end
    )
    / nullif(count(*), 0),
    2
)
```

Valeur observée lors de la création :

```text
100 %
```

### Exécutions des pipelines

Compte le nombre de runs Airflow enregistrés.

```sql
count(*)
```

Valeur initiale :

```text
5
```

Répartition :

```text
Vélib : 2
Trafic routier : 3
```

### Durée moyenne d’une ingestion

```sql
round(
    avg(duration_seconds),
    2
)
```

Valeur initiale :

```text
8.85 secondes
```

### Observations reçues

```sql
sum(records_received)
```

Valeur initiale :

```text
26 864
```

Cette valeur représente le volume cumulé reçu, y compris les
observations reconnues comme déjà présentes lors des relances
idempotentes.

## Visualisations

### Évolution de la durée des ingestions

Type :

```text
Line Chart
```

Configuration :

```text
X-Axis : started_at
Metric : AVG(duration_seconds)
Dimension : pipeline_name
Granularité : minute
```

Les marqueurs et la légende sont activés.

Les valeurs sont accessibles au survol afin d’éviter les
chevauchements avec les axes.

Le graphique permet de comparer les performances des pipelines
Vélib et trafic routier.

### Volumes traités par pipeline

Type :

```text
Bar Chart
```

Axe :

```text
pipeline_name
```

Métriques enregistrées dans le dataset :

```text
Reçues
Insérées
Inchangées
```

Ce graphique distingue :

- le volume transmis par l’API ;
- les nouvelles données réellement insérées ;
- les observations déjà connues grâce à l’idempotence.

### Dernières exécutions des pipelines

Type :

```text
Table
```

Colonnes :

```text
pipeline_name
started_at
status
records_received
records_inserted
records_updated
records_unchanged
duration_seconds
records_per_second
```

Tri :

```text
started_at décroissant
```

Limite :

```text
20 exécutions
```

## Filtres interactifs

### Pipeline

Colonne :

```text
pipeline_name
```

Valeurs :

```text
Vélib
Trafic routier
```

### Statut

Colonne :

```text
status
```

Valeurs :

```text
success
failed
```

Les deux filtres s’appliquent à l’ensemble des KPI et graphiques.

Exemple validé :

```text
Tous les pipelines : 5 exécutions
Vélib : 2 exécutions
Trafic routier : 3 exécutions
```

## Disposition

Organisation recommandée :

```text
Ligne 1
KPI Taux de succès
KPI Exécutions
KPI Durée moyenne
KPI Observations reçues

Ligne 2
Évolution de la durée
Volumes traités par pipeline

Ligne 3
Dernières exécutions des pipelines
```

Le tableau détaillé utilise toute la largeur disponible.

## Export reproductible

Le dashboard a été exporté depuis Superset puis décompressé dans :

```text
superset/exports/monitoring_platform
```

L’export contient :

- les métadonnées ;
- la connexion `Mobility Warehouse` ;
- le dataset `fct_pipeline_runs` ;
- le dashboard ;
- les sept graphiques.

Le mot de passe PostgreSQL n’est pas présent dans l’export.
Superset l’a remplacé par :

```text
XXXXXXXXXX
```

Un mot de passe valide devra être fourni lors d’un futur import.

## Import futur

Pour réimporter le dashboard :

1. compresser le contenu de
   `superset/exports/monitoring_platform` ;
2. ouvrir Superset ;
3. aller dans l’import des dashboards ;
4. sélectionner l’archive ;
5. fournir le mot de passe du warehouse si demandé ;
6. vérifier la connexion et le dataset ;
7. contrôler les filtres et la disposition.

## Tests

Résultats validés :

```text
fct_pipeline_runs : créé avec succès
Tests dbt : 18 réussis
Erreurs dbt : 0
Connexion Superset/PostgreSQL : réussie
Dashboard : fonctionnel
Filtres Pipeline et Statut : fonctionnels
Export Superset : complet
Secret PostgreSQL dans l’export : absent
```

## Limites connues

Le suivi repose actuellement sur un faible nombre de runs locaux.
Les graphiques deviendront plus représentatifs après plusieurs jours
d’exécution planifiée.

Le rate limiting de Superset utilise encore un stockage en mémoire.
Cela reste acceptable pour une instance locale unique, mais devra être
réévalué avant une exposition publique à forte fréquentation.

## Suite

Les prochains dashboards seront :

1. disponibilité Vélib ;
2. trafic routier parisien ;
3. vue d’ensemble Mobilité Paris.

Le dashboard Monitoring servira également à vérifier la santé de la
plateforme après son futur déploiement sur la VM OVH.