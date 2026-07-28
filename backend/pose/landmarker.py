"""Envoltorio de MediaPipe Pose Landmarker (variante pesada, modo imagen).

Aisla toda la dependencia de MediaPipe en un solo sitio. Devuelve los
landmarks como listas de dicts serializables, sin tocar la base de datos.
"""

from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

RUTA_MODELO = Path(__file__).resolve().parents[2] / "data" / "models" / "pose_landmarker_heavy.task"
VERSION_MODELO = "pose_landmarker_heavy/float16"
MAX_FIGURAS = 5  # detecta hasta 5 para poder contar y elegir principal


def _lm_a_dicts(landmark_list) -> list[dict]:
    return [
        {
            "x": round(p.x, 6),
            "y": round(p.y, 6),
            "z": round(p.z, 6),
            "visibility": round(getattr(p, "visibility", 0.0), 4),
            "presence": round(getattr(p, "presence", 0.0), 4),
        }
        for p in landmark_list
    ]


class DetectorPose:
    """Carga el modelo una vez y lo reutiliza para todo el lote."""

    def __init__(self, ruta_modelo: Path = RUTA_MODELO):
        if not ruta_modelo.exists():
            raise FileNotFoundError(
                f"No se encuentra el modelo en {ruta_modelo}. "
                "Descargalo (ver instrucciones de la fase 3)."
            )
        opciones = vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(ruta_modelo)),
            running_mode=vision.RunningMode.IMAGE,
            num_poses=MAX_FIGURAS,
            output_segmentation_masks=False,
        )
        self._detector = vision.PoseLandmarker.create_from_options(opciones)

    def detectar(self, ruta_imagen: Path) -> tuple[list[list[dict]], list[list[dict]]]:
        """Devuelve (figuras_2d, figuras_3d). Cada figura es su lista de
        landmarks. Listas vacias si no se detecto ninguna."""
        img = cv2.imread(str(ruta_imagen))
        if img is None:
            raise ValueError("no se pudo leer la imagen")
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)

        res = self._detector.detect(mp_image)
        figuras_2d = [_lm_a_dicts(lm) for lm in res.pose_landmarks]
        figuras_3d = [_lm_a_dicts(lm) for lm in res.pose_world_landmarks]
        return figuras_2d, figuras_3d

    def cerrar(self) -> None:
        self._detector.close()
