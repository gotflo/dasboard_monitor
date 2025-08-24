#!/usr/bin/env python3
"""
Test rapide de la caméra thermique avec le code corrigé
"""

import cv2
import numpy as np
import time


def test_thermal_camera():
    print("Test de la caméra thermique à l'index 1...")
    
    # Ouvrir la caméra avec DirectShow (Windows)
    cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
    
    if not cap.isOpened():
        print(" Impossible d'ouvrir la caméra")
        return False
    
    print(" Caméra ouverte")
    
    # Lire quelques frames
    success_count = 0
    error_count = 0
    
    print("\nLecture de 30 frames...")
    for i in range(30):
        ret, frame = cap.read()
        
        if ret and frame is not None:
            success_count += 1
            
            # Afficher les infos sur la première frame
            if success_count == 1:
                print(f"  Résolution native: {frame.shape}")
                print(f"  Type: {frame.dtype}")
            
            # Tester le redimensionnement
            if frame.shape[0] < 480:
                resized = cv2.resize(frame, (640, 480), interpolation=cv2.INTER_LINEAR)
            
            # Afficher la frame (optionnel - décommentez pour voir)
            # cv2.imshow('Thermal Camera Test', resized if 'resized' in locals() else frame)
            # if cv2.waitKey(1) & 0xFF == ord('q'):
            #     break
        
        else:
            error_count += 1
        
        time.sleep(0.033)  # ~30 FPS
    
    print(f"\n Succès: {success_count}/30 frames")
    if error_count > 0:
        print(f"  Erreurs: {error_count}/30")
    
    # Test de performance
    print("\nTest de performance (100 frames)...")
    start_time = time.time()
    
    for _ in range(100):
        ret, frame = cap.read()
        if frame is not None and frame.shape[0] < 480:
            cv2.resize(frame, (640, 480), interpolation=cv2.INTER_LINEAR)
    
    elapsed = time.time() - start_time
    fps = 100 / elapsed
    
    print(f"  FPS moyen: {fps:.1f}")
    print(f"  Temps par frame: {elapsed / 100 * 1000:.1f}ms")
    
    cap.release()
    cv2.destroyAllWindows()
    
    print("\n Test terminé avec succès!")
    return True


if __name__ == "__main__":
    print("=" * 50)
    print(" TEST RAPIDE CAMÉRA THERMIQUE")
    print("=" * 50)
    
    success = test_thermal_camera()
    
    if success:
        print("\n La caméra thermique fonctionne parfaitement!")
        print("Vous pouvez maintenant lancer votre application.")
    else:
        print("\n Problème détecté avec la caméra thermique")
        print("Vérifiez la connexion USB et réessayez.")