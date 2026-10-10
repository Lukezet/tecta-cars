# Requerimientos: Conteo diario de servicios de lavado

## Resumen (3-5 oraciones)

El sistema debe observar una única zona de trabajo mediante una cámara Tapo C510W y contabilizar como servicio cada vehículo que permanezca continuamente dentro de esa zona durante al menos 15 minutos. Debe admitir uno o dos vehículos simultáneos, registrar cada uno de forma independiente y conservar como evidencia una imagen, el color estimado y la patente cuando pueda reconocerse. El operador podrá configurar visualmente la zona, consultar los servicios del día y corregir el conteo manualmente. Los datos se conservarán localmente aunque la aplicación o la PC se reinicien; la integración con la API del sistema de lavados se realizará en una fase posterior.

## Problema que resuelve

El conteo diario de servicios se realiza o verifica manualmente y puede contener omisiones o diferencias. El sistema debe producir un total local confiable y auditable a partir de la permanencia real de vehículos en la zona de trabajo, generando evidencia útil antes de automatizar el registro en el sistema externo.

## Usuarios y contexto de uso

En el MVP, un operador o responsable del lavadero utilizará la aplicación desde una PC de la instalación, conectada a la misma red local que la cámara. Configurará la zona cuando se instale o mueva la cámara y consultará durante el día el estado de los vehículos, el total y el historial. El producto podrá comercializarse en el futuro, pero esta versión cubre una instalación, una cámara y una zona; no incluye aún gestión centralizada de clientes, sucursales o usuarios.

## Historias de usuario

Como responsable del lavadero, quiero dibujar y guardar la zona de trabajo sobre la imagen de la cámara para que el sistema observe únicamente el espacio donde se realizan servicios.

- Criterios de aceptación (verificables, formato "Dado/Cuando/Entonces" cuando aplique):
  - [ ] Dada una imagen disponible de la cámara, cuando el operador configura la zona, entonces puede delimitarla visualmente y guardar la configuración.
  - [ ] Dada una zona guardada, cuando se reinicia la aplicación o la PC, entonces la zona continúa configurada.
  - [ ] Dada una cámara que cambió de posición, cuando la imagen ya no coincide con la referencia configurada, entonces el operador puede volver a calibrar la zona antes de reanudar el conteo.
  - [ ] La interfaz comunica que la cámara debe permanecer fija y sin patrullaje automático durante el conteo.

Como responsable del lavadero, quiero que cada vehículo que permanezca continuamente 15 minutos dentro de la zona se contabilice una sola vez para conocer los servicios realizados durante el día.

- Criterios de aceptación (verificables, formato "Dado/Cuando/Entonces" cuando aplique):
  - [ ] Dado un vehículo dentro de la zona durante menos de 15 minutos continuos, cuando abandona la zona, entonces no incrementa el conteo.
  - [ ] Dado un vehículo dentro de la zona, cuando alcanza 15 minutos de permanencia continua, entonces el total diario aumenta exactamente en uno.
  - [ ] Dado un vehículo ya contabilizado que permanece dentro de la zona, cuando transcurren más cuadros o más tiempo, entonces no vuelve a contabilizarse.
  - [ ] Dados dos vehículos presentes simultáneamente, cuando cada uno alcanza 15 minutos continuos, entonces cada vehículo genera un servicio independiente.
  - [ ] Dado que la aplicación se reinicia durante una jornada, cuando vuelve a abrirse, entonces conserva los servicios ya confirmados y no reduce el total persistido.
  - [ ] Dado un vehículo que abre o cierra puertas, capó o baúl durante el lavado, cuando su forma visual cambia o el seguimiento técnico le asigna otro identificador, entonces conserva una única identidad lógica y el tiempo acumulado.
  - [ ] Dadas varias detecciones visuales que corresponden al mismo vehículo físico, cuando aparecen simultáneamente, entonces se consolidan en un solo vehículo activo y un solo temporizador.
  - [ ] Dado un vehículo ya contabilizado que cambia de apariencia por sus partes móviles, entonces no vuelve a contabilizarse.
  - [ ] La patente, el color, la posición y la continuidad temporal pueden contribuir a conservar la identidad, pero la patente no es obligatoria ni constituye la única señal.
  - [ ] La interfaz muestra identificadores lógicos estables y comprensibles, no los identificadores internos y transitorios del tracker.

Como responsable del lavadero, quiero configurar la cantidad máxima de vehículos que caben simultáneamente en la zona para adaptar el sistema a cada instalación y evitar conteos físicamente imposibles.

- Criterios de aceptación (verificables, formato "Dado/Cuando/Entonces" cuando aplique):
  - [ ] La configuración permite indicar una capacidad máxima entera positiva para la zona de trabajo.
  - [ ] En este lavadero la capacidad se configura inicialmente en `2` vehículos simultáneos.
  - [ ] Dada una capacidad configurada en `N`, cuando el detector produzca más de `N` tracks o detecciones, entonces el sistema nunca crea más de `N` vehículos lógicos ni más de `N` temporizadores activos.
  - [ ] Dado que ya existen `N` vehículos lógicos activos, una detección adicional no inicia otro temporizador hasta que se determine que pertenece a uno de ellos o quede disponible una posición real.
  - [ ] Cambiar la capacidad queda disponible para instalaciones que admitan uno, tres o más vehículos, sin modificar el código.
  - [ ] La capacidad configurada persiste después de reiniciar la aplicación o la PC.

Como operador, quiero ver el estado actual para saber qué vehículos están siendo observados y cuánto falta para que cada uno se convierta en servicio.

- Criterios de aceptación (verificables, formato "Dado/Cuando/Entonces" cuando aplique):
  - [ ] La pantalla principal muestra la imagen en vivo, la zona superpuesta, el estado de conexión y el total del día.
  - [ ] Por cada vehículo activo muestra el tiempo continuo acumulado y si está pendiente o contabilizado.
  - [ ] Si no hay cámara, zona o video disponible, la pantalla explica el problema y la acción necesaria.

Como operador, quiero consultar la evidencia de cada servicio para revisar el conteo.

- Criterios de aceptación (verificables, formato "Dado/Cuando/Entonces" cuando aplique):
  - [ ] Cada servicio automático guarda la fecha y hora exacta en que alcanzó los 15 minutos.
  - [ ] Cada servicio guarda al menos una captura del vehículo.
  - [ ] Cada servicio muestra el color estimado.
  - [ ] Si la patente pudo detectarse y leerse con confianza suficiente, el servicio muestra su texto y un recorte; si no, indica "patente no reconocida" sin impedir el conteo.
  - [ ] El historial permite consultar los servicios correspondientes al día actual en orden cronológico.

Como operador, quiero sumar o restar manualmente servicios para corregir errores sin perder trazabilidad.

- Criterios de aceptación (verificables, formato "Dado/Cuando/Entonces" cuando aplique):
  - [ ] El operador puede agregar una corrección de `+1` o `-1` al total diario.
  - [ ] Toda corrección solicita una confirmación y registra fecha, hora, tipo de ajuste y motivo.
  - [ ] El total mostrado distingue los servicios automáticos de los ajustes manuales.
  - [ ] Un ajuste negativo no permite que el total diario final quede por debajo de cero.

Como responsable del sistema, quiero conectar la Tapo C510W de manera segura para evitar exponer sus credenciales.

- Criterios de aceptación (verificables, formato "Dado/Cuando/Entonces" cuando aplique):
  - [ ] La cámara se consume mediante `stream2` dentro de la red local.
  - [ ] La contraseña no aparece en archivos versionados, documentación, argumentos, mensajes de error ni logs.
  - [ ] Un fallo de conexión informa el estado sin revelar credenciales.

## Requerimientos no funcionales

- El conteo debe operar localmente sin depender de Internet ni de la futura API del sistema de lavados.
- La información confirmada, los ajustes, la zona configurada y las evidencias deben persistir ante reinicios de la aplicación o de la PC.
- La cámara debe permanecer fija; cualquier movimiento requiere revisar o recalibrar la zona.
- La interfaz será en español y deberá mostrar estados de carga, vacío, conexión y error.
- Las acciones interactivas deberán ser accesibles por teclado, tener foco visible y no depender únicamente del color.
- La contraseña de la cámara deberá permanecer fuera del repositorio y de toda salida visible.
- La patente y el color son datos auxiliares: un fallo en su estimación no debe impedir contabilizar un servicio válido.
- El MVP debe registrar hasta dos vehículos simultáneos dentro de la única zona de trabajo.
- La cantidad máxima de vehículos simultáneos debe ser configurable por instalación; su valor inicial en este lavadero es `2`.
- Un identificador producido por el tracker es un dato técnico transitorio y no debe utilizarse directamente como identidad del vehículo ni como unidad de conteo.

## Restricciones

- Una cámara Tapo C510W conectada por RTSP dentro de la red local de cada instalación.
- Una única zona de trabajo configurable en esta versión.
- Umbral fijo inicial de 15 minutos de permanencia continua.
- El conteo se confirma al alcanzar el umbral, no al salir del lavadero.
- El desarrollo actual utiliza Python, OpenCV, Ultralytics YOLO y EasyOCR.
- En este momento de análisis la PC no está conectada a la red Wi-Fi de la cámara; las validaciones visuales se harán al recuperar esa conexión.
- El MVP se ejecuta en una PC local de una instalación, aunque su arquitectura deberá admitir evolución comercial posterior.

## Fuera de alcance (versión actual)

- Reconocer como el mismo servicio a un vehículo que sale y vuelve a ingresar.
- Resolver movimientos LIFO o reordenamiento temporal de dos vehículos.
- Acumular tiempo de permanencias separadas.
- Más de una cámara, zona, lavadero o sucursal por instalación.
- Gestión de usuarios, roles, clientes, licencias comerciales o plataforma central en la nube.
- Envío del conteo a la API del sistema de lavados.
- Control PTZ, patrullaje automático o reposicionamiento automático de la cámara.
- Lectura perfecta u obligatoria de patentes y colores.
- Acceso remoto directo a la cámara desde Internet.

## Riesgos y dudas abiertas

- Dos vehículos parcialmente superpuestos pueden dificultar el seguimiento independiente.
- Un mismo vehículo con puertas, capó o baúl abiertos puede generar varias detecciones o cambios de track; el piloto debe verificar que se mantenga una sola identidad lógica y un solo temporizador.
- Oclusiones, personal, reflejos, lluvia o mala iluminación pueden interrumpir visualmente una permanencia que en la realidad fue continua; se deberá medir este comportamiento con casos reales.
- El movimiento físico o PTZ de la cámara invalida la relación entre la imagen y la zona guardada.
- Una dirección IP asignada dinámicamente puede cambiar; deberá evaluarse una reserva DHCP para operación estable.
- El reconocimiento de patente puede fallar por ángulo, tamaño, suciedad o iluminación y no debe utilizarse como única identidad en este MVP.
- Antes de comercializar el producto será necesario definir privacidad, retención de imágenes, usuarios, soporte, actualizaciones y operación para múltiples instalaciones.

## Priorización (MoSCoW: Must / Should / Could / Won't)

### Must

- Configurar y persistir una zona de trabajo.
- Mostrar la cámara y la zona en la interfaz.
- Seguir independientemente hasta dos vehículos en el caso regular.
- Configurar la capacidad máxima simultánea de la zona y respetarla como límite estricto de vehículos lógicos activos.
- Mantener una identidad lógica estable aunque cambie el ID técnico del tracker o se abran partes móviles del vehículo.
- Contabilizar una vez al alcanzar 15 minutos continuos.
- Persistir total, servicios, ajustes y evidencias localmente.
- Mostrar total diario e historial con hora, imagen, color y patente opcional.
- Permitir ajustes manuales `+1` y `-1` con motivo y trazabilidad.
- Mantener seguras las credenciales de cámara.

### Should

- Mostrar el tiempo restante de cada vehículo activo.
- Advertir claramente cuando falten cámara, conexión o zona.
- Facilitar la recalibración después de mover la cámara.
- Conservar una imagen de referencia de la configuración de zona.

### Could

- Detectar automáticamente un posible cambio de encuadre y pausar el conteo.
- Permitir revisar imágenes ampliadas desde el historial.
- Reservar la IP de la cámara desde el router.

### Won't

- Resolver salidas y reingresos como continuidad del mismo servicio.
- Integrarse con la API del sistema de lavados en este MVP.
- Implementar múltiples instalaciones, nube o administración comercial.
