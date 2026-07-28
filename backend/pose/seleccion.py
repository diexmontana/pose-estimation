"""Seleccion determinista de la figura principal y agregacion de
visibilidad por zonas. Sin dependencia de MediaPipe, para poder probarlo
aislado.

Regla de la figura principal (seccion 7.5): la de mayor area de bounding
box; si empatan, la mas a la izquierda. Debe ser siempre la misma para
que los resultados no cambien entre ejecuciones.
"""

# Indices de los 33 landmarks de MediaPipe Pose agrupados por zona.
ZONAS = {
    "cabeza": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "torso": [11, 12, 23, 24],
    "brazos": [13, 14, 15, 16],
    "manos": [17, 18, 19, 20, 21, 22],
    "piernas": [25, 26, 27, 28],
    "pies": [29, 30, 31, 32],
}


def _bbox(landmarks: list[dict]) -> tuple[float, float, float, float]:
    xs = [p["x"] for p in landmarks]
    ys = [p["y"] for p in landmarks]
    return min(xs), min(ys), max(xs), max(ys)


def elegir_figura_principal(figuras: list[list[dict]]) -> int:
    """Devuelve el indice de la figura elegida. `figuras` es una lista de
    poses; cada pose es la lista de sus landmarks 2D normalizados."""
    if not figuras:
        raise ValueError("no hay figuras")

    mejor_idx = 0
    mejor_area = -1.0
    mejor_x = 1.0
    for idx, lm in enumerate(figuras):
        x0, y0, x1, y1 = _bbox(lm)
        area = (x1 - x0) * (y1 - y0)
        # mayor area; empate -> menor x0 (mas a la izquierda)
        if area > mejor_area or (area == mejor_area and x0 < mejor_x):
            mejor_idx, mejor_area, mejor_x = idx, area, x0
    return mejor_idx


def visibilidad_por_zonas(landmarks: list[dict]) -> dict[str, float]:
    """Media de visibilidad de cada zona a partir de los landmarks 2D."""
    resultado = {}
    for zona, indices in ZONAS.items():
        vals = [landmarks[i].get("visibility", 0.0) for i in indices]
        resultado[zona] = round(sum(vals) / len(vals), 4) if vals else 0.0
    return resultado
