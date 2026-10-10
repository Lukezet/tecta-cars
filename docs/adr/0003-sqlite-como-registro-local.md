# ADR-0003: Usar SQLite como registro local

- **Estado:** aceptada
- **Contexto:** zona, servicios y ajustes deben sobrevivir reinicios, mantener integridad y permitir auditoría cronológica sin desplegar infraestructura adicional.
- **Decisión:** usar SQLite mediante `sqlite3`, migraciones SQL versionadas, constraints e índices. El total diario se deriva de servicios y ajustes; las imágenes quedan en disco con rutas relativas.
- **Alternativas consideradas:** JSON/CSV son más simples pero frágiles ante concurrencia y correcciones; PostgreSQL facilita centralización futura pero es sobrearquitectura para una instalación local.
- **Consecuencias:** no se requiere servidor de base de datos y existe una ruta de migración futura. Se necesitan backups, migraciones probadas, transacciones breves y un único escritor coordinado.
