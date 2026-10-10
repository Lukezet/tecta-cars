# ADR-0002: Usar una interfaz web local separada del motor

- **Estado:** aceptada
- **Contexto:** el procesamiento y los temporizadores deben continuar aunque el operador recargue o cierre la vista. La interfaz necesita video, dibujo de polígonos, historial y posibilidad de evolucionar comercialmente.
- **Decisión:** ejecutar FastAPI y el motor en un monolito modular local enlazado a `127.0.0.1`, con HTML/CSS/JavaScript sin framework de Node para el MVP. El video se entrega como MJPEG y el estado mediante endpoints JSON.
- **Alternativas consideradas:** PySide6 ofrece escritorio nativo pero agrega peso y acoplamiento; Streamlit acelera prototipos pero su modelo de reejecución no favorece un motor continuo; una SPA separada ofrece más escala, pero agrega toolchain prematuramente.
- **Consecuencias:** el navegador puede recargarse sin perder conteo y la UI puede evolucionar; se agregan FastAPI/Uvicorn y debe asegurarse que el servidor no se exponga fuera de localhost en el MVP.
