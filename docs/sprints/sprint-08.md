# Sprint 8 — Rétention contrôlée des données

## Objectif

Mettre en place une politique de rétention sécurisée pour maîtriser la
croissance de PostgreSQL sans perdre les tendances historiques nécessaires aux
analyses.

La rétention doit rester :

- simulable avant exécution ;
- protégée par une sauvegarde restaurée et vérifiée ;
- transactionnelle ;
- compatible avec les modèles dbt incrémentaux ;
- réversible grâce aux sauvegardes ;
- explicitement autorisée avant toute suppression.

## Politique de rétention

La politique configurée par défaut est :

| Données | Conservation |
|---|---:|
| RAW selon `ingested_at` | 30 jours |
| Faits détaillés selon `status_updated_at` | 24 mois |
| Monitoring selon `started_at` | 12 mois |
| Agrégats quotidiens | Conservation longue durée |
| Dimension des stations | État courant |

Ces valeurs peuvent être remplacées avec les variables suivantes :

```text
RAW_RETENTION_DAYS
FACT_RETENTION_MONTHS
MONITORING_RETENTION_MONTHS
```

Seuls des entiers strictement positifs sont acceptés.

## Script de rétention

Le script suivant a été ajouté :

```text
scripts/apply_data_retention.sh
```

Par défaut, il fonctionne uniquement en mode simulation :

```bash
./scripts/apply_data_retention.sh
```

La simulation :

1. affiche la politique active ;
2. compte les lignes candidates ;
3. vérifie la présence des agrégats quotidiens ;
4. n’exécute aucune suppression.

## Résultat de la simulation

Résultat observé avant la première exécution :

```text
raw_rows_candidate = 0
fact_rows_candidate = 1
monitoring_rows_candidate = 0
daily_rows_preserved = 1720
```

La seule observation détaillée candidate était :

```text
station_id = 8116
station_name = Champs-Elysees - Bassano
status_updated_at = 2021-02-21 19:09:18
loaded_at = 2026-07-17 22:29:59.243734
```

L’agrégat quotidien correspondant existait avant la suppression.

## Protection des agrégats

Avant toute exécution, le script recherche les faits expirés qui ne possèdent
pas d’agrégat quotidien correspondant.

Si au moins une ligne n’est pas agrégée, la rétention est interrompue.

Cette protection empêche de supprimer le dernier niveau de détail disponible
avant la création de sa représentation longue durée.

Les lignes de `agg_velib_station_daily` ne sont jamais supprimées par le
script de rétention.

## Sauvegarde vérifiée obligatoire

Le script de restauration du Sprint 7 a été étendu.

Après une restauration temporaire réussie, il crée désormais un marqueur :

```text
<archive>.dump.verified
```

Ce marqueur contient :

```text
backup
sha256
verified_at_utc
```

Le mode exécution de la rétention exige :

- l’archive PostgreSQL ;
- le fichier SHA-256 ;
- le marqueur de vérification ;
- une vérification réalisée depuis moins de 24 heures ;
- une correspondance entre l’archive, le checksum et le marqueur.

La somme SHA-256 est recalculée avant la transaction.

## Protections du mode exécution

Pour exécuter réellement la rétention, les trois conditions suivantes sont
obligatoires :

1. option `--execute` ;
2. option `--verified-backup` avec une archive valide ;
3. variable de confirmation exacte :

```text
RETENTION_CONFIRMATION=DELETE_EXPIRED_MOBILITY_DATA
```

Exemple :

```bash
RETENTION_CONFIRMATION=DELETE_EXPIRED_MOBILITY_DATA \
./scripts/apply_data_retention.sh \
  --execute \
  --verified-backup \
  backups/postgresql/<archive>.dump
```

Sans sauvegarde, le script s’arrête avec :

```text
Error: --verified-backup is required in execute mode.
```

Sans confirmation, le script s’arrête avec :

```text
Error: RETENTION_CONFIRMATION is missing or invalid.
```

## Transaction PostgreSQL

Les suppressions sont exécutées dans une transaction unique :

```text
BEGIN
DELETE RAW
DELETE FACTS
DELETE MONITORING
COMMIT
```

Si une requête échoue, PostgreSQL annule l’ensemble de la transaction.

Après validation, le script exécute `ANALYZE` sur les tables concernées afin
d’actualiser les statistiques utilisées par l’optimiseur PostgreSQL.

## Protection contre les full-refresh

Le macro suivant a été ajouté :

```text
dbt_mobility/macros/prevent_unapproved_full_refresh.sql
```

Il protège les modèles historiques suivants :

```text
fct_velib_status
agg_velib_station_daily
```

Une commande dbt contenant `--full-refresh` est bloquée par défaut avec une
erreur de compilation.

Cette protection évite de reconstruire accidentellement la table de faits à
partir d’un RAW ayant déjà subi une rétention.

Une exception volontaire reste disponible :

```bash
dbt compile \
  --full-refresh \
  --select fct_velib_status \
  --vars '{"allow_destructive_full_refresh": true}'
```

L’utilisation de cette variable avec `dbt run` nécessite impérativement :

- une sauvegarde restaurée et vérifiée ;
- une analyse d’impact ;
- une autorisation explicite ;
- une procédure de restauration disponible.

## Adaptation du test quotidien

Le test suivant a été adapté :

```text
assert_daily_aggregate_matches_fact
```

Avant la rétention, il exigeait une correspondance dans les deux directions
entre la table de faits et les agrégats.

Après la rétention, un agrégat quotidien peut légitimement être plus ancien que
le détail encore conservé.

Le test vérifie désormais que :

- chaque groupe encore présent dans `fct_velib_status` possède un agrégat ;
- son nombre d’observations correspond exactement ;
- un agrégat ancien peut survivre sans détail associé.

## Première rétention exécutée

La suppression réelle a été autorisée explicitement après :

- une sauvegarde PostgreSQL ;
- une restauration temporaire réussie ;
- une vérification SHA-256 ;
- une simulation ;
- un contrôle des agrégats ;
- une validation complète des modèles dbt.

Résultat de la transaction :

```text
raw_rows_deleted = 0
fact_rows_deleted = 1
monitoring_rows_deleted = 0
```

La transaction a été validée avec succès.

## Contrôles après rétention

Contrôle de l’observation de la station `8116` :

```text
raw_rows_preserved = 1
fact_rows_remaining = 0
daily_rows_preserved = 1
expired_fact_rows_remaining = 0
```

La ligne RAW reste présente parce que son horodatage technique d’ingestion est
récent.

Le détail analytique datant de 2021 a été supprimé.

L’agrégat quotidien du 21 février 2021 reste conservé.

## Validation incrémentale après suppression

Le pipeline dbt a été relancé après la rétention.

Résultat :

```text
PASS = 56
WARN = 1
ERROR = 0
SKIP = 0
TOTAL = 57
```

La fraîcheur de la source RAW a également réussi.

Contrôle final :

```text
fact_rows = 5030
aggregated_observations = 5031
purged_fact_recreated = 0
historical_daily_preserved = 1
```

Le modèle incrémental n’a pas recréé la ligne purgée.

La différence d’une ligne entre le détail et les agrégats est attendue : elle
représente l’observation historique désormais conservée uniquement au niveau
quotidien.

## Opérations non automatisées

Ce sprint ne planifie pas encore la rétention automatiquement.

La commande reste volontairement manuelle jusqu’au déploiement OVH afin de
valider :

- la fréquence des sauvegardes ;
- le stockage externe ;
- les alertes ;
- les fenêtres de maintenance ;
- l’espace réellement consommé ;
- la politique commune aux quatre projets de la VM.

## Sécurité

Le script ne contient aucun mot de passe.

Les identifiants PostgreSQL restent fournis au conteneur par les variables
d’environnement de Docker Compose.

Les archives, checksums et marqueurs de vérification sont stockés dans le
dossier `backups/`, exclu de Git.

La base active peut être restaurée à partir de l’archive vérifiée utilisée avant
la rétention.

## Fichiers concernés

Fichiers créés :

- `scripts/apply_data_retention.sh` ;
- `dbt_mobility/macros/prevent_unapproved_full_refresh.sql` ;
- `docs/sprints/sprint-08.md`.

Fichiers modifiés :

- `scripts/verify_warehouse_backup.sh` ;
- `scripts/backup_warehouse.sh` ;
- `dbt_mobility/models/marts/fct_velib_status.sql` ;
- `dbt_mobility/models/marts/agg_velib_station_daily.sql` ;
- `dbt_mobility/tests/assert_daily_aggregate_matches_fact.sql` ;
- `docs/sprints/sprint-07.md`.

Les modifications de `scripts/backup_warehouse.sh` et de
`docs/sprints/sprint-07.md` ajoutent uniquement leur saut de ligne final
manquant.

## Suite

Les prochaines étapes prévues sont :

- définir la planification sur OVH ;
- chiffrer et externaliser les sauvegardes ;
- définir une rotation locale ;
- ajouter les alertes d’échec ;
- surveiller la croissance réelle de PostgreSQL ;
- intégrer les données de trafic routier parisien.