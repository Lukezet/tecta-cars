# ADR-0004: Usar ByteTrack y permanencia continua por track

- **Estado:** aceptada
- **Contexto:** deben medirse de forma independiente uno o dos vehículos durante 15 minutos, evitando contar cada cuadro. El MVP no une salidas y reingresos.
- **Decisión:** usar ByteTrack incluido en Ultralytics con `persist=True`, cámara fija y una máquina de estados por ID. Un servicio se confirma una vez al alcanzar 900 segundos continuos dentro del polígono, con una gracia inicial de 10 segundos para pérdidas visuales breves.
- **Alternativas consideradas:** BoT-SORT/ReID puede resistir mejor algunas oclusiones pero consume más recursos; un tracker propio por IoU es más frágil; usar la patente como identidad excluye vehículos cuya matrícula no se lea.
- **Consecuencias:** se implementa rápido sobre el stack actual y funciona sin patente. Los cambios de ID siguen siendo un riesgo que debe medirse con videos reales; la gracia será configurable y el reingreso se tratará en una fase posterior.
