import cv2
import svgwrite
import numpy as np

class ArucoSvgGenerator:
    def __init__(self, output_filename="aruco_board.svg"):
        self.filename = output_filename
        # Dimensioni standard A4 in mm
        self.page_width = 210
        self.page_height = 297
        self.dwg = svgwrite.Drawing(self.filename, size=(f'{self.page_width}mm', f'{self.page_height}mm'))
        
        # Mappa dei dizionari ArUco più comuni
        self.dict_map = {
            "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
            "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
            "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
            "DICT_6X6_250": cv2.aruco.DICT_6X6_250,
            "DICT_7X7_1000": cv2.aruco.DICT_7X7_1000,
            # Aggiungi altri se necessario
        }

    def generate(self, dict_name, markers_x, markers_y, marker_size_mm, gap_mm):
        """
        Genera la griglia ArUco su file SVG.
        
        :param dict_name: Stringa del nome del dizionario (es. "DICT_4X4_50")
        :param markers_x: Numero di marker sull'asse X (colonne)
        :param markers_y: Numero di marker sull'asse Y (righe)
        :param marker_size_mm: Dimensione del lato del marker (incluso bordo nero) in mm
        :param gap_mm: Spazio tra i marker in mm
        """
        
        # 1. Caricamento Dizionario
        if dict_name not in self.dict_map:
            raise ValueError(f"Dizionario {dict_name} non trovato. Usa uno tra: {list(self.dict_map.keys())}")
        
        aruco_dict = cv2.aruco.getPredefinedDictionary(self.dict_map[dict_name])
        
        # Calcolo dimensioni totali della griglia per centrarla
        total_grid_width = (markers_x * marker_size_mm) + ((markers_x - 1) * gap_mm)
        total_grid_height = (markers_y * marker_size_mm) + ((markers_y - 1) * gap_mm)
        
        # Calcolo margini per centrare nel foglio A4
        start_x = (self.page_width - total_grid_width) / 2
        start_y = (self.page_height - total_grid_height) / 2
        
        if start_x < 0 or start_y < 0:
            print("ATTENZIONE: La griglia è troppo grande per un foglio A4!")

        id_counter = 0
        
        # 2. Ciclo di generazione
        for y in range(markers_y):
            for x in range(markers_x):
                # Posizione corrente in mm
                curr_x = start_x + x * (marker_size_mm + gap_mm)
                curr_y = start_y + y * (marker_size_mm + gap_mm)
                
                # Genera l'immagine del singolo marker (matrice di bit)
                # sidePixels=1 permette di ottenere solo i bit puri senza scaling
                # NOTA: La dimensione della matrice bit dipende dal dizionario (es. 4x4 + 2 bordi = 6x6)
                marker_bits = cv2.aruco.generateImageMarker(aruco_dict, id_counter, sidePixels=10) 
                
                # Per avere i bit esatti senza interpolazione, usiamo la dimensione base del dizionario
                # Esempio: 4x4 ha bisogno di 2 bit di bordo nero, quindi 6x6
                # Ricaviamo la dimensione in bit (celle) del marker
                marker_cell_count = marker_bits.shape[0] 
                
                # Dimensione di ogni singola celletta (bit) in mm
                cell_size_mm = marker_size_mm / marker_cell_count
                
                self._draw_marker_svg(marker_bits, curr_x, curr_y, cell_size_mm)
                
                id_counter += 1
                
        self.dwg.save()
        print(f"File salvato correttamente come: {self.filename}")

    def _draw_marker_svg(self, marker_image, offset_x, offset_y, cell_size):
        """Disegna il marker bit per bit nel file SVG"""
        rows, cols = marker_image.shape
        
        # ArUco genera immagini dove 0 è nero e 255 è bianco.
        # In SVG disegniamo solo i quadrati neri.
        for r in range(rows):
            for c in range(cols):
                if marker_image[r, c] == 0:  # Se è nero
                    x_pos = offset_x + (c * cell_size)
                    y_pos = offset_y + (r * cell_size)
                    
                    self.dwg.add(self.dwg.rect(
                        insert=(f'{x_pos}mm', f'{y_pos}mm'),
                        size=(f'{cell_size}mm', f'{cell_size}mm'),
                        fill='black'
                    ))


if __name__ == "__main__":
    # Parametri Modulari
    DICT_ARUCO = "DICT_4X4_50"  # 1. Tipo di dizionario
    DIMENSIONE_MARKER = 35.0    # 2a. Dimensione marker (mm)
    SPAZIO_TRA_MARKER = 5.0     # 2b. Spazio interno/gap (mm)
    NUM_X = 4                   # 3a. Marker su X
    NUM_Y = 6                   # 3b. Marker su Y
    
    # Esecuzione
    generator = ArucoSvgGenerator("board_a4.svg")
    generator.generate(
        dict_name=DICT_ARUCO, 
        markers_x=NUM_X, 
        markers_y=NUM_Y, 
        marker_size_mm=DIMENSIONE_MARKER, 
        gap_mm=SPAZIO_TRA_MARKER
    )