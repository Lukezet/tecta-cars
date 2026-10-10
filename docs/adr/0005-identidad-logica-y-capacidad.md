# ADR-0005: Separar la identidad lógica de los tracks y limitarla por capacidad

- **Estado:** aceptada
- **Contexto:** durante el primer uso real, un automóvil con puertas y baúl abiertos recibió varios IDs de ByteTrack y produjo varios temporizadores simultáneos. Los IDs técnicos llegaron a valores como 2341 y 2827 y se mostraron como si fueran vehículos diferentes. Este lavadero admite como máximo dos automóviles en la zona, pero otras instalaciones pueden admitir uno, tres o más.
- **Decisión:** introducir una capa de identidad lógica entre ByteTrack y el contador. La capa consolida detecciones compatibles, reasocia cambios de track mediante posición, continuidad temporal, patente y color, y entrega identificadores estables al contador y a la interfaz. La zona tendrá una capacidad máxima positiva persistida, inicialmente `2`; no podrán existir más identidades lógicas ni temporizadores activos que esa capacidad. La base impedirá contar dos veces el mismo `logical_vehicle_id` dentro de una sesión, mientras conserva el `tracker_id` solo para diagnóstico.
- **Alternativas consideradas:**
  - Aumentar únicamente la gracia de desaparición: conserva el track viejo pero permite que el nuevo acumule tiempo en paralelo, por lo que no evita el doble conteo.
  - Recortar la detección al cuerpo central: reduce el efecto de puertas abiertas, pero puede perder señales útiles y no resuelve por sí mismo los cambios de ID ni las cajas duplicadas.
  - Usar la patente como identidad única: funciona cuando la lectura es correcta, pero no es confiable en todos los ángulos y condiciones.
  - Reemplazar ByteTrack por ReID: agrega costo y recursos sin garantizar que una silueta alterada por partes móviles conserve identidad; podrá evaluarse si la capa local no alcanza.
- **Consecuencias:** el conteo deja de depender del ID transitorio del tracker y respeta límites físicos configurables. Se agrega estado de asociación, una migración de datos y pruebas específicas. La calibración deberá equilibrar dos errores opuestos: unir dos autos cercanos o separar un solo auto en varias identidades. Las salidas y reingresos reales continúan fuera del alcance actual.
