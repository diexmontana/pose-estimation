# Guía de reglas de clasificación automática

Documento de referencia para **calibrar** la detección. Explica, por categoría,
qué regla y qué umbrales deciden cada etiqueta, y en qué dirección mover cada
umbral. Todos los umbrales están en el diccionario `U` de
`backend/tagging/reglas.py`.

**Ciclo de trabajo** (no necesita base de datos ni servidor):

1. Genera las copias con ángulos y el "por qué" por imagen:
   `python -m backend.tagging.depurar_carpeta "C:\ruta\a\carpeta"`
   (salida en la carpeta hermana `..._debug`).
2. Abre una imagen y su `.md`: verás la etiqueta, el umbral que decidió y el
   valor medido (p. ej. *cadera_max 128° ≤ cadera_sentado(130) [le faltan 22°…]*).
3. Decide: si el valor está **cerca del corte**, mueve el umbral; si está
   **lejos**, es un fallo de MediaPipe (no lo arregla ningún umbral).
4. Cambia el valor en `U` (`reglas.py`) y reejecuta el mismo comando: es
   instantáneo (reusa la caché). `--reanalizar` fuerza rehacer MediaPipe.

> **Bandas de incertidumbre**: si un valor cae en la zona muerta entre dos
> clases, la categoría no se etiqueta y va a *revisión*. Por eso a veces la
> etiqueta correcta es "que quede en revisión", no forzarla.

---

## Landmarks de MediaPipe (referencia)

MediaPipe Pose devuelve 33 puntos. Los que usamos:

| Nº | Punto | Nº | Punto |
|---|---|---|---|
| 0 | nariz | 7 / 8 | oreja izq / der |
| 11 / 12 | hombro izq / der | 13 / 14 | codo izq / der |
| 15 / 16 | muñeca izq / der | 23 / 24 | cadera izq / der |
| 25 / 26 | rodilla izq / der | 27 / 28 | tobillo izq / der |
| 29 / 30 | talón izq / der | 31 / 32 | punta de pie izq / der |

Cada punto trae además una **visibilidad** (0 a 1) que dice cuánta confianza
tiene MediaPipe en ese punto.

Dos marcos de referencia:
- **Ángulos articulares**: se calculan en 3D (metros, "world landmarks"), así son
  ángulos reales en el espacio, no en la foto.
- **Inclinaciones, ratios y dispersiones**: se calculan en 2D sobre la imagen
  (en píxeles, corrigiendo la proporción con el ancho y alto reales).

---

## Cómo se calcula cada medida

**Ángulos articulares** (grados). Es el ángulo que forman tres puntos en el del
medio. Fórmula: `ángulo = arccos( (BA · BC) / (|BA|·|BC|) )`, donde B es la
articulación y A, C los puntos vecinos. 180° = estirado, 90° = doblado en
escuadra. Landmarks:

- **codo izq / der**: hombro–codo–muñeca → 11-13-15 / 12-14-16
- **rodilla izq / der**: cadera–rodilla–tobillo → 23-25-27 / 24-26-28
- **hombro izq / der** (apertura del brazo): codo–hombro–cadera → 13-11-23 / 14-12-24
- **cadera izq / der** (muslo vs torso): hombro–cadera–rodilla → 11-23-25 / 12-24-26

**inclinacion_torso** (grados). Ángulo entre el "eje del torso" y la vertical de
la imagen. El eje del torso va del punto medio de las caderas al punto medio de
los hombros: `mid_cadera = (23+24)/2`, `mid_hombro = (11+12)/2`. 0° = torso
recto; ~90° = tumbado.

**ratio_hombros_torso** (número). Es una **división**: anchura de hombros entre
largo del torso → `distancia(11,12) / distancia(mid_hombro, mid_cadera)`. Sirve
para orientación: al girar el cuerpo, los hombros se ven más estrechos y el ratio
baja. Es más fiable que el ancho a secas porque al dividir por el torso se cancela
el tamaño de la persona.

**Visibilidad de zonas** (`pies`, `piernas`, etc., de 0 a 1). Es el **promedio**
de la visibilidad que MediaPipe da a los puntos de esa zona:
- `pies` = promedio de la visibilidad de 29, 30, 31, 32.
- `piernas` = promedio de 25, 26, 27, 28.
- `torso` = 11, 12, 23, 24 · `cabeza` = 0 a 10 · `brazos` = 13, 14, 15, 16.

Por eso `encuadre_pies` y `encuadre_piernas` son umbrales sobre ese promedio: si
la zona de los pies supera 0.25, se considera que hay pie en cuadro.

**Escorzo** (por miembro, número cercano a 1). Compara lo que se ve el miembro en
2D contra lo que mide de verdad en 3D. Es una **división de proporciones**:
`(largo_2D / torso_2D) / (largo_3D / torso_3D)`. Para el brazo, `largo` =
distancia(hombro,codo) + distancia(codo,muñeca). ≈ 1 = sin escorzo; < 1 = el
miembro se ve más corto de lo que mide (apunta hacia/desde la cámara).

**extension** (número). Mide cuánto se separan los miembros del centro del cuerpo.
Es el **promedio** de las distancias de muñecas y tobillos (15, 16, 27, 28) al
centro del cuerpo, **dividido** por el largo del torso (para no depender del
tamaño). Alta = pose abierta/dinámica; baja = pose recogida.

**dispersion_vertical / horizontal** (número). Cuánto se reparten los puntos
visibles en vertical y en horizontal. Es la **desviación** de las coordenadas Y
(o X) de los puntos, dividida por el largo del torso. Se usa para "acostado":
cuando la dispersión horizontal supera a la vertical, la figura está tumbada.

**vis_nariz, vis_oreja_izq/der** (0 a 1). La visibilidad directa de la nariz (0)
y las orejas (7, 8). La **asimetría de orejas** = `|vis_oreja_izq − vis_oreja_der|`
(una **resta** en valor absoluto): si solo se ve una oreja, la persona está de
perfil o de tres cuartos.

**ratio_torso_piernas** (número, solo 2D). **División** del largo del torso entre
el largo de las piernas en la imagen: `distancia(mid_hombro, mid_cadera) /
promedio(distancia(23,27), distancia(24,28))` (cadera→tobillo). Usa solo puntos
visibles, nada del eje z. En un **picado** (cámara arriba) las piernas se ven más
cortas y este ratio sube; en **contrapicado** baja. Base del ángulo de cámara.

---

## Postura

Señal principal: el **ángulo de cadera** (hombro–cadera–rodilla). Abierta ≈ de
pie; flexionada ≈ sentado. Las rodillas por sí solas no distinguen. Se evalúa en
este orden:

1. **acostado** — si el torso está tumbado (`inclinacion_torso` > `acostado_torso`=55°)
   **y** la figura es más ancha que alta (`disp_h` > `disp_v` × `acostado_factor`=1.3).
2. **en cuclillas** — ambas rodillas muy flexionadas (≤ `cuclillas_rodilla`=70°),
   **los pies no cruzados**, y la cadera no abierta.
3. **de pie** — cadera más abierta ≥ `cadera_abierta`=150° y torso casi vertical
   (< `postura_torso_vertical`=40°).
4. **inclinado** — cadera ≥ `cadera_abierta` pero el torso inclinado (≥ 40°).
5. **arrodillado** — una rodilla al piso (< `cuclillas_rodilla`) y la otra
   extendida (≥ `de_pie_rodilla`=150°).
6. **sentado** — cadera ≤ `cadera_sentado`=130°.
7. Cadera entre 130° y 150° sin señal clara → **revisión**.

## Encuadre

Basado en qué zonas del cuerpo son visibles:

- **primer plano** — no hay torso fiable (triaje), o solo se ve la cabeza.
- **cuerpo completo** — un pie en cuadro (`pies` ≥ `encuadre_pies`=0.25) **o** las
  piernas (`piernas` ≥ `encuadre_piernas`=0.5).
- **plano medio** — torso visible pero sin piernas/pies.
- *plano americano* y *plano de detalle* no son automáticos: se ponen a mano.

## Orientación corporal

Combina la anchura de hombros y la visibilidad de orejas:

- **de espaldas** — nariz oculta (< 0.4) y sin dos orejas visibles.
- **de frente** — dos orejas visibles y `ratio_hombros_torso` ≥ `orient_ratio_frente`=0.60.
- **perfil** — asimetría de orejas ≥ `orient_oreja_asim`=0.40 y ratio < `orient_ratio_perfil`=0.40.
- **tres cuartos** — asimetría de orejas alta pero sin llegar a perfil, o ratio
  entre 0.40 y 0.60.
- Sin señal clara → **revisión**.

## Escorzo

- **nivel** (del miembro más escorzado): < 0.65 → *pronunciado*; 0.65–0.85 →
  *leve*; > 0.85 → *ninguno* (umbral `escorzo_cortes`, banda `escorzo_banda`=0.03).
- **miembro escorzado** (múltiple): cada miembro con ratio < `escorzo_miembro`=0.80.

## Dinamismo

Desde la `extension` (cuánto se separan los miembros del centro): < 0.95 →
*estática*; 0.95–1.40 → *moderada*; > 1.40 → *dinámica* (umbral
`dinamismo_cortes`, banda `dinamismo_banda`=0.06).

## Ángulo de cámara (pista de baja confianza)

Solo se evalúa **de pie con caderas y rodillas rectas** (ambas ≥ `camara_recto`=160°),
para no confundir el acortamiento de las piernas por la pose con el del ángulo de
cámara. Usa solo landmarks 2D visibles (nada del eje z, que no es fiable):

- **picado** — `ratio_torso_piernas` > 0.9 (las piernas se ven cortas → cámara arriba).
- **a nivel** — ratio entre 0.5 y 0.9.
- **contrapicado** — ratio < 0.5 (las piernas se ven largas → cámara abajo).
- (umbral `camara_cortes`=[0.5, 0.9], banda `camara_banda`=0.05).

Umbrales **provisionales**: son los primeros candidatos a calibrar con el modo
depuración, porque dependen de las proporciones del cuerpo. Es una pista de baja
confianza; lo dudoso va a revisión.

---

## Tabla: qué umbral mover y en qué dirección

| Umbral (`U`) | Valor | Qué controla | Súbelo si… | Bájalo si… |
|---|---|---|---|---|
| `cadera_abierta` | 150 | frontera de "de pie" | salen "de pie" figuras que no lo están | figuras de pie caen en "sentado"/revisión |
| `cadera_sentado` | 130 | frontera de "sentado" | sentados claros quedan en revisión | salen "sentado" figuras que no lo están |
| `postura_torso_vertical` | 40 | de pie vs inclinado | marca "inclinado" a gente recta | marca "de pie" a gente muy inclinada |
| `cuclillas_rodilla` | 70 | flexión para "cuclillas"/"arrodillado" (además, pies no cruzados) | sentados normales salen "cuclillas" | no detecta cuclillas reales |
| `acostado_torso` | 55 | torso tumbado para "acostado" | poses de acción anchas salen "acostado" | tumbados de verdad no se detectan |
| `acostado_factor` | 1.3 | anchura para "acostado" | (igual que arriba, más estricto) | (más permisivo) |
| `encuadre_pies` | 0.25 | un pie → cuerpo entero | pies apenas visibles cuentan como cuerpo entero | se pierden cuerpos enteros con pies poco visibles |
| `encuadre_piernas` | 0.5 | piernas → cuerpo entero | piernas poco visibles cuentan | se pierden cuerpos enteros |
| `orient_ratio_frente` | 0.60 | frontera "de frente" | menos casos "de frente" | más casos "de frente" |
| `orient_ratio_perfil` | 0.40 | frontera "perfil" | más casos "perfil" | menos casos "perfil" |
| `orient_oreja_asim` | 0.40 | asimetría para perfil/3-4 | hace falta más asimetría (más conservador) | detecta 3/4 con poca asimetría |
| `escorzo_cortes` | 0.65 / 0.85 | leve vs pronunciado vs ninguno | sube el listón de "pronunciado"/"leve" | baja el listón |
| `escorzo_miembro` | 0.80 | marca un miembro como escorzado | marca más miembros | marca menos |
| `dinamismo_cortes` | 0.95 / 1.40 | estática/moderada/dinámica | hace falta más extensión para "dinámica" | menos extensión |
| `camara_recto` | 160 | cuándo se evalúa el ángulo de cámara | solo poses muy rectas lo evalúan | evalúa aunque haya algo de flexión |
| `camara_cortes` | 0.5 / 0.9 | contrapicado / a nivel / picado | hace falta más acortamiento para "picado" | marca "picado" con menos |
| `vis` | 0.6 | visibilidad mínima de una zona | exige zonas más nítidas | acepta zonas más borrosas |

*Nota: si cambias `medidas.py` (la geometría, no un umbral), reejecuta el
comando con `--reanalizar` para rehacer las medidas.*
