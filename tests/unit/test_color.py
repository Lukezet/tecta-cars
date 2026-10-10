import unittest

import numpy as np

from detecta_images.engine import estimate_color


class VehicleColorTests(unittest.TestCase):
    def test_red_body_wins_over_large_gray_windshield(self) -> None:
        image = np.full((200, 300, 3), (70, 70, 70), dtype=np.uint8)
        image[95:165, 25:275] = (45, 55, 155)
        image[20:105, 55:245] = (125, 115, 105)

        color = estimate_color(image, (0, 0, 300, 200))

        self.assertEqual(color, "rojo")

    def test_dark_blue_body_is_not_reduced_to_black(self) -> None:
        image = np.full((200, 300, 3), (20, 20, 20), dtype=np.uint8)
        image[85:165, 25:275] = (55, 25, 15)

        color = estimate_color(image, (0, 0, 300, 200))

        self.assertEqual(color, "azul")

    def test_achromatic_body_remains_gray(self) -> None:
        image = np.full((200, 300, 3), (120, 120, 120), dtype=np.uint8)

        color = estimate_color(image, (0, 0, 300, 200))

        self.assertEqual(color, "gris")

    def test_nearer_red_vehicle_does_not_contaminate_black_vehicle(self) -> None:
        image = np.full((240, 320, 3), (18, 18, 18), dtype=np.uint8)
        image[100:200, 40:280] = (35, 35, 35)
        image[80:230, 180:320] = (40, 45, 155)

        color = estimate_color(
            image,
            (20, 20, 280, 220),
            excluded_bounds=[(180, 80, 320, 230)],
        )

        self.assertEqual(color, "negro")


if __name__ == "__main__":
    unittest.main()
