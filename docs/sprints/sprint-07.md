# Sprint 7 — Sauvegarde et restauration PostgreSQL

## Objectif

Mettre en place une sauvegarde logique, compressée et vérifiable de l’entrepôt
PostgreSQL, puis valider sa restauration complète dans une base temporaire.

Ce sprint ne modifie pas la base active pendant la restauration de test et
n’active aucune suppression automatique des sauvegardes.

## Base concernée

La sauvegarde concerne l’entrepôt métier utilisé par le pipeline :

```text
Service Docker : postgres_destination
Base : mobility_warehouse
Image : postgres:15-alpine
Volume : postgres_destination_data
```

Les bases de métadonnées Airflow et Superset ne sont pas incluses dans ce
premier mécanisme. Elles pourront utiliser la même approche dans un futur
sprint d’exploitation.

## Choix de la sauvegarde logique

La sauvegarde est créée avec `pg_dump` au format PostgreSQL personnalisé :

```text
format = custom
compression = 6
no-owner
no-privileges
```

Ce format permet :

- une sauvegarde cohérente pendant que PostgreSQL fonctionne ;
- une compression intégrée ;
- une vérification de la structure avec `pg_restore --list` ;
- une restauration dans une base différente ;
- une restauration sélective si nécessaire ;
- une meilleure portabilité qu’une copie directe du volume Docker.

## Script de sauvegarde

Le script suivant a été ajouté :

```text
scripts/backup_warehouse.sh
```

Il réalise les étapes suivantes :

1. localise automatiquement la racine du projet ;
2. vérifie que `postgres_destination` fonctionne ;
3. crée le dossier de sauvegarde si nécessaire ;
4. exécute `pg_dump` depuis le conteneur PostgreSQL ;
5. écrit d’abord l’archive dans un fichier temporaire ;
6. vérifie que l’archive n’est pas vide ;
7. valide sa structure avec `pg_restore --list` ;
8. renomme atomiquement le fichier temporaire ;
9. calcule une somme de contrôle SHA-256.

Le dossier par défaut est :

```text
backups/postgresql/
```

Il peut être remplacé avec la variable :

```text
BACKUP_DIRECTORY
```

## Nommage des sauvegardes

Les archives utilisent un horodatage UTC :

```text
mobility_warehouse_YYYYMMDDTHHMMSSZ.dump
```

Chaque archive possède un fichier de contrôle associé :

```text
mobility_warehouse_YYYYMMDDTHHMMSSZ.dump.sha256
```

Les permissions locales sont limitées grâce à :

```text
umask 077
```

## Exclusion Git

Le dossier suivant est exclu du contrôle de version :

```text
backups/
```

Les archives PostgreSQL peuvent contenir l’intégralité des données métier.
Elles ne doivent jamais être ajoutées dans Git.

## Script de vérification et restauration

Le script suivant a été ajouté :

```text
scripts/verify_warehouse_backup.sh
```

Il prend le chemin d’une archive en argument :

```bash
./scripts/verify_warehouse_backup.sh \
  backups/postgresql/mobility_warehouse_YYYYMMDDTHHMMSSZ.dump
```

Le script réalise les contrôles suivants :

1. vérification de la présence de l’archive ;
2. vérification de la somme SHA-256 ;
3. validation de la structure PostgreSQL ;
4. création d’une base temporaire ;
5. restauration complète de l’archive ;
6. contrôle des relations obligatoires ;
7. affichage du nombre de lignes restaurées ;
8. suppression automatique de la base temporaire.

## Protection de la base active

La restauration de vérification ne cible jamais directement :

```text
mobility_warehouse
```

Une base temporaire est créée avec un nom de la forme :

```text
mobility_restore_verify_YYYYMMDDTHHMMSSZ_PID
```

Une fonction de nettoyage est exécutée à la fin du script, y compris lorsqu’une
erreur interrompt la vérification après la création de la base.

La base active reste disponible et inchangée pendant toute l’opération.

## Relations contrôlées

La restauration est considérée valide uniquement si les relations suivantes
existent :

```text
schema_raw.stg_raw_stations
schema_analytics.dim_stations
schema_analytics.fct_velib_status
schema_analytics.agg_velib_station_daily
schema_monitoring.ingestion_runs
```

## Test local réalisé

Archive testée :

```text
mobility_warehouse_20260718T005914Z.dump
```

Résultat de la somme de contrôle :

```text
OK
```

Résultat de la restauration temporaire :

| Relation | Nombre de lignes restaurées |
|---|---:|
| RAW Vélib | 5 031 |
| Table de faits | 5 031 |
| Dimension des stations | 1 516 |
| Agrégats quotidiens | 1 720 |
| Monitoring des ingestions | 2 |

Résultat final :

```text
Backup restoration verified successfully.
```

La base temporaire a ensuite été supprimée automatiquement.

## Vérifications techniques

Les deux scripts ont été validés avec :

```bash
bash -n scripts/backup_warehouse.sh
bash -n scripts/verify_warehouse_backup.sh
```

La sauvegarde a été créée depuis PostgreSQL 15, puis restaurée dans une autre
base PostgreSQL du même conteneur.

## Utilisation locale

Créer une sauvegarde :

```bash
./scripts/backup_warehouse.sh
```

Vérifier et restaurer temporairement la sauvegarde :

```bash
./scripts/verify_warehouse_backup.sh \
  backups/postgresql/<archive>.dump
```

## Limites actuelles

Ce sprint ne met pas encore en place :

- une planification Airflow ou système ;
- une rotation automatique ;
- une suppression des anciennes sauvegardes ;
- un stockage externe ;
- le chiffrement des archives ;
- une restauration automatique sur la base active ;
- la sauvegarde des métadonnées Airflow ;
- la sauvegarde des métadonnées Superset.

Ces fonctions nécessitent une politique d’exploitation et une validation
supplémentaire avant le déploiement OVH.

## Recommandations pour OVH

Lors du déploiement, les sauvegardes ne devront pas rester uniquement sur le
disque du VPS.

La stratégie cible devra inclure :

- une petite rotation locale ;
- une copie vers un stockage externe ;
- un chiffrement avant transfert ;
- une vérification périodique par restauration ;
- une alerte en cas d’échec ;
- une documentation de reprise après incident.

## Fichiers concernés

Fichiers créés :

- `scripts/backup_warehouse.sh` ;
- `scripts/verify_warehouse_backup.sh` ;
- `docs/sprints/sprint-07.md`.

Fichier modifié :

- `.gitignore`.

## Suite

Les prochaines étapes prévues sont :

- définir la rotation locale ;
- préparer un stockage externe ;
- automatiser les sauvegardes ;
- mesurer la croissance de l’entrepôt ;
- définir et valider la rétention des données ;
- protéger les opérations `dbt --full-refresh`.