CONTAINER_NAME = care-db-1
DB_NAME = dicom
DB_USER = postgres

SQL_TB_CREATE = ./sql-scripts/10_create-psql.sql
SQL_FK_CREATE = ./sql-scripts/20_create-fk-index.sql
SQL_IDX_CREATE = ./sql-scripts/30_create-case-insensitive-index.sql
# SH_COLLAPSE_CONFIG = psql-set-collapse-limit.sh

PSQL = docker exec -i $(CONTAINER_NAME) psql -U $(DB_USER) -d $(DB_NAME)

.PHONY: setup-dicom-db start stop

start:
	docker compose -f '../care-be/docker-compose.yaml' -f docker-compose.yaml up -d

stop:
	docker compose -f '../care-be/docker-compose.yaml' -f docker-compose.yaml down

restart:
	docker compose -f '../care-be/docker-compose.yaml' -f docker-compose.yaml restart

setup-dicom-db:
	@echo "Running SQL scripts..."
	@$(PSQL) < $(SQL_TB_CREATE)
	@$(PSQL) < $(SQL_FK_CREATE)
	@$(PSQL) < $(SQL_IDX_CREATE)
	@echo "Done!"

ldap-setup:
	ldapmodify -x -D "cn=admin,dc=dcm4che,dc=org" -H ldap://localhost:3890 -W -f bucketconfig.ldif