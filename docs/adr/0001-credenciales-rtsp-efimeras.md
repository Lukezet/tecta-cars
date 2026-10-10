# ADR-0001: Usar credenciales RTSP efímeras con entrada oculta

- **Estado:** aceptada
- **Contexto:** OpenCV necesita una URL RTSP autenticada, pero colocar la contraseña en `--stream` la expone en el historial de PowerShell, la lista de procesos y los logs actuales. El MVP se ejecuta manualmente desde una sola PC y todavía no requiere operación desatendida.
- **Decisión:** solicitar la contraseña mediante un prompt oculto del helper, entregarla al proceso por entrada estándar y construir la URL codificada solamente en memoria. Los mensajes usarán una descripción sin credenciales. No se guardará el secreto en archivos, variables persistentes ni argumentos del proceso.
- **Alternativas consideradas:**
  - URL completa en `--stream`: es compatible con el código actual, pero expone el secreto en múltiples superficies y queda descartada.
  - Variables de entorno: evitan el argumento visible, pero pueden heredarse a procesos hijos y quedar configuradas accidentalmente; son útiles para automatización futura, no para este MVP interactivo.
  - Archivo `.env` ignorado por Git: facilita reinicios, pero deja la contraseña almacenada en texto claro y agrega gestión innecesaria para una primera prueba.
  - Gestor de credenciales de Windows: ofrece mejor persistencia segura, pero aumenta la complejidad y no es necesario hasta automatizar la ejecución continua.
- **Consecuencias:** la prueba manual protege la contraseña sin dependencias nuevas y no permite inicio totalmente desatendido. La operación continua futura deberá reemplazar el prompt por Windows Credential Manager u otro almacén de secretos.
